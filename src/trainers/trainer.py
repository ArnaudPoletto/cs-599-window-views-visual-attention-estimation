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

from src.metrics.metrics import Metrics
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
        super(Trainer, self).__init__()

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
    def _get_wandb_config(self) -> dict[str, any]:
        raise NotImplementedError

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

        total_train_loss = 0
        n_train_loss = 0
        for batch_idx, batch in enumerate(train_loader):
            # Zero the gradients
            optimizer.zero_grad()
            temporal_train_loss, global_train_loss, _, _, _, _ = self._forward_pass(batch)
            train_loss = temporal_train_loss + global_train_loss
            total_train_loss += train_loss.item()
            n_train_loss += 1

            scaler.scale(train_loss).backward()

            # Optimize every accumulation steps
            if (batch_idx + 1) % self.accumulation_steps == 0:
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

            if (batch_idx + 1) % self.evaluation_steps == 0:
                # Get and update training loss
                self.eval_train_loss = total_train_loss / n_train_loss
                total_train_loss = 0
                n_train_loss = 0

                # Get validation loss and update best model
                stats = self._evaluate(val_loader)
                self.eval_val_loss = stats["loss"]
                if (
                    self.eval_val_loss < self.best_eval_val_loss
                    and save_path is not None
                ):
                    print(
                        f"🎉 Saving model with new best loss: {self.eval_val_loss:.4f}"
                    )
                    torch.save(self.model.state_dict(), save_path)
                    self.best_eval_val_loss = self.eval_val_loss

                bar.set_postfix(
                    {
                        "batch": f"{batch_idx + 1}/{len(train_loader)}",
                        "train_loss": f"{self.eval_train_loss:.4f}",
                        "val_loss": f"{self.eval_val_loss:.4f}",
                    }
                )

                # Log to WandB all statistics
                stats = {key: value for key, value in stats.items() if key != "loss"}
                stats.update({"train_loss": self.eval_train_loss, "val_loss": self.eval_val_loss})
                wandb.log(stats)

    def _evaluate(self, loader: DataLoader) -> dict[str, float]:
        self.model.eval()

        with torch.no_grad():
            metrics = {}
            for batch in loader:
                # Get loss and metrics
                temporal_val_loss, global_val_loss, temporal_output, global_output, temporal_ground_truth, global_ground_truth = self._forward_pass(batch)

                if "temporal_loss" not in metrics:
                    metrics["temporal_loss"] = []
                metrics["temporal_loss"].append(temporal_val_loss.item())
                if "global_loss" not in metrics:
                    metrics["global_loss"] = []
                metrics["global_loss"].append(global_val_loss.item())

                new_temporal_metrics = Metrics().get_metrics(temporal_output, temporal_ground_truth, center_bias_prior=None) # TODO: add center bias prior
                for key, value in new_temporal_metrics.items():
                    if key not in metrics:
                        metrics[f"temporal_{key}"] = []
                    metrics[f"temporal_{key}"].append(value)
                new_global_metrics = Metrics().get_metrics(global_output, global_ground_truth, center_bias_prior=None) # TODO: add center bias prior
                for key, value in new_global_metrics.items():
                    if key not in metrics:
                        metrics[f"global_{key}"] = []
                    metrics[f"global_{key}"].append(value)

        # Normalize metrics
        for key, value in metrics.items():
            metrics[key] = torch.mean(torch.tensor(value)).item()

        self.model.train()

        return metrics

    def _get_name(self, optimizer: Optimizer, n_epochs: int, learning_rate: int) -> str:
        return self.name

    def train(
        self,
        train_loader: DataLoader,
        val_loader: DataLoader,
        optimizer: Optimizer,
        n_epochs: int,
        learning_rate: int,
        save_model: bool = True,
    ) -> None:
        # Get name with timestamp
        name = self._get_name(optimizer, n_epochs, learning_rate)
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        name = f"{timestamp}_{name}"

        # Create a folder with the name of the model
        model_path = (
            f"{Path(MODELS_PATH).resolve()}/{self.model.__class__.__name__.lower()}"
        )
        os.makedirs(model_path, exist_ok=True)

        save_path = f"{model_path}/{name}.pth" if save_model else None

        # Setup WandB and watch
        wandb_config = self._get_wandb_config()
        wandb_config.update(
            {
                "n_epochs": n_epochs,
                "learning_rate": learning_rate,
            }
        )
        wandb.init(
            project="thesis",
            group=self.__class__.__name__.lower(),
            name=name,
            config=wandb_config,
        )
        wandb.watch(self.model, log_freq=4, log="all")

        print(f"🚀 Training {self.__class__.__name__} method for {n_epochs} epochs...")
        # model number traininable
        print(
            f"🔧 Model has {sum(p.numel() for p in self.model.parameters() if p.requires_grad):,} trainable parameters"
        )

        # Scaler
        scaler = GradScaler(enabled=self.use_scaler)

        # Training loop
        self.model.train()
        with tqdm(range(n_epochs), desc="⌛ Running epochs...", unit="epoch") as bar:
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
