import torch
from torch import nn
from typing import Dict, Any
from torch.optim import Optimizer
from torch.cuda.amp import autocast

from src.trainers.trainer import Trainer

from src.config import DEVICE

class LiveSALTrainer(Trainer):
    def __init__(
        self,
        model: nn.Module,
        criterion: nn.Module,
        accumulation_steps: int,
        evaluation_steps: int,
        use_scaler: bool,
        name: str,
    ) -> None:
        super(LiveSALTrainer, self).__init__(
            model=model,
            criterion=criterion,
            accumulation_steps=accumulation_steps,
            evaluation_steps=evaluation_steps,
            use_scaler=use_scaler,
            name=name,
        )

    def _get_wandb_config(self) -> Dict[str, Any]:
        return {
            "model_name": self.model.__class__.__name__,
            "hidden_channels": self.model.hidden_channels,
            "output_channels": self.model.output_channels,
            "with_absolute_positional_embeddings": self.model.with_absolute_positional_embeddings,
            "with_relative_positional_embeddings": self.model.with_relative_positional_embeddings,
            "n_heads": self.model.n_heads,
            "neighbor_radius": self.model.neighbor_radius,
            "n_iterations": self.model.n_iterations,
            "with_graph_processing": self.model.with_graph_processing,
            "freeze_encoder": self.model.freeze_encoder,
            "with_depth_information": self.model.with_depth_information,
            "fusion_level": self.model.fusion_level,

        }

    def _get_name(
        self, optimizer: Optimizer, n_epochs: int, learning_rate: float
    ) -> str:
        name = self.name

        return name

    def _forward_pass(self, batch: tuple) -> torch.Tensor:
        frame, ground_truths, global_ground_truth = batch
        frame = frame.float().to(DEVICE)
        ground_truths = ground_truths.float().to(DEVICE)
        global_ground_truth = global_ground_truth.float().to(DEVICE)

        # Forward pass
        with autocast(enabled=self.use_scaler):
            outputs = self.model(frame)

        if self.model.output_channels == 1:
            ground_truth = global_ground_truth
        else:
            ground_truth = ground_truths
        loss = self.criterion(outputs, ground_truth)

        # Compute loss
        return loss, None, None # TODO: return None for now