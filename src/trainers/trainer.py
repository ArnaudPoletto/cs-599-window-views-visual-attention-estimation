import sys
from pathlib import Path

GLOBAL_DIR = Path(__file__).parent / ".." / ".."
sys.path.append(str(GLOBAL_DIR))

import os
import time
import wandb
import torch
import numpy as np
from torch import nn
from tqdm import tqdm
from typing import Tuple
from torch.optim import Optimizer
from abc import ABC, abstractmethod
from torch.cuda.amp import GradScaler
from torch.utils.data import DataLoader

from src.config import MODELS_PATH


class Trainer(ABC):
    def __init__(
        self,
        model: nn.Module,
        criterion: nn.Module,
        accumulation_steps: int,
        evaluation_steps: int,
        use_scaler: bool,
        name: str,
    ) -> None:
        self.model = model
        self.criterion = criterion
        self.accumulation_steps = accumulation_steps
        self.evaluation_steps = evaluation_steps
        self.use_scaler = use_scaler
        self.name = name

        self.best_eval_val_loss = np.inf
        self.eval_train_loss = 0
        self.eval_val_loss = 0

    @abstractmethod
    def _forward_pass(
        self, batch: tuple
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        raise NotImplementedError

    def _train_one_epoch(
        self,
        train_loader: DataLoader,
        val_loader: DataLoader,
        optimizer: Optimizer,
        scaler: GradScaler,
        bar: tqdm,
        save_path: str = None,
    ) -> None:
        self.model.train()

        total_train_loss = 0
        n_train_loss = 0
        for batch_idx, batch in enumerate(train_loader):
            # Zero the gradients
            optimizer.zero_grad()
            train_loss, _, _ = self._forward_pass(batch)
            total_train_loss += train_loss.item()
            n_train_loss += 1

            scaler.scale(train_loss).backward()

            # Optimize every accumulation steps
            if ((batch_idx + 1) % self.accumulation_steps == 0) or (
                batch_idx + 1 == len(train_loader)
            ):
                scaler.step(optimizer)
                scaler.update()

            if bar is not None:
                bar.set_postfix(
                    {
                        "batch": f"{batch_idx + 1}/{len(train_loader)}",
                        "train_loss": f"{self.eval_train_loss:.4f}",
                        "val_loss": f"{self.eval_val_loss:.4f}",
                    }
                )

            if (batch_idx + 1) % self.evaluation_steps == 0 or (
                batch_idx + 1 == len(train_loader)
            ):
                # Get and update training loss
                self.eval_train_loss = total_train_loss / n_train_loss
                total_train_loss = 0
                n_train_loss = 0

                # Get validation loss and update best model
                stats = self._evaluate(val_loader)
                self.eval_val_loss = stats["loss"]
                if self.eval_val_loss < self.best_eval_val_loss and save_path is not None:
                    print(f"🎉 Saving model with new best loss: {self.eval_val_loss:.4f}")
                    torch.save(self.model.state_dict(), save_path)
                    self.best_eval_val_loss = self.eval_val_loss

                bar.set_postfix(
                    {
                        "batch": f"{batch_idx + 1}/{len(train_loader)}",
                        "train_loss": f"{self.eval_train_loss:.4f}",
                        "val_loss": f"{self.eval_val_loss:.4f}",
                    }
                )
                wandb.log(
                    {
                        "train_loss": self.eval_train_loss,
                        "val_loss": self.eval_val_loss,
                    }
                )

    def _evaluate(self, loader: DataLoader) -> dict[str, float]:
        self.model.eval()

        total_val_loss = 0
        with torch.no_grad():
            for batch in loader:
                val_loss, _, _ = self._forward_pass(batch)
                total_val_loss += val_loss.item()
        total_val_loss /= len(loader)

        statistics = {
            "loss": total_val_loss,
        }

        return statistics

    def _get_name(
        self, optimizer: Optimizer, num_epochs: int, learning_rate: int
    ) -> str:
        return self.name

    def train(
        self,
        train_loader: DataLoader,
        val_loader: DataLoader,
        optimizer: Optimizer,
        num_epochs: int,
        learning_rate: int,
        save_model: bool = True,
    ) -> None:
        # Get name with timestamp
        name = self._get_name(optimizer, num_epochs, learning_rate)
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        name = f"{timestamp}_{name}"

        # Create a folder with the name of the model
        model_path = (
            f"{Path(MODELS_PATH).resolve()}/{self.model.__class__.__name__.lower()}"
        )
        os.makedirs(model_path, exist_ok=True)

        save_path = f"{model_path}/{name}.pth" if save_model else None

        # Setup WandB and watch
        wandb.init(
            project=self.__class__.__name__.lower(),
            config={
                "architecture": self.__class__.__name__,
                "name": name,
                "dataset": "Window View",
                "epochs": num_epochs,
                "learning_rate": learning_rate,
            },
        )
        wandb.watch(self.model, log_freq=4, log="all")

        print(
            f"🚀 Training {self.__class__.__name__} method for {num_epochs} epochs..."
        )

        # Scaler
        scaler = GradScaler(enabled=self.use_scaler)

        # Training loop
        with tqdm(range(num_epochs), desc="⌛ Running epochs...", unit="epoch") as bar:
            for _ in bar:
                self._train_one_epoch(
                    train_loader,
                    val_loader,
                    optimizer,
                    scaler,
                    bar,
                    save_path=save_path,
                )

        wandb.unwatch(self.model)
        wandb.finish()