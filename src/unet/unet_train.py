# This script is used to train the UNet model.

import sys
from pathlib import Path

GLOBAL_DIR = Path(__file__).parent / ".." / ".."
sys.path.append(str(GLOBAL_DIR))

import os
import torch
import torch.nn as nn

os.environ["KMP_DUPLICATE_LIB_OK"] = "True"

from src.models.unet import UNet
from src.utils.random import set_seed
from src.trainers.unet_trainer import UNetTrainer
from src.datasets.sequence_dataset import get_dataloaders
from src.utils.file import get_sample_paths_list
from src.config import SEED, DEVICE

SEQUENCE_LENGTH = 5
WITH_TRANSFORMS = True
BATCH_SIZE = 2
SPLITS = (0.9, 0.05, 0.05)
TRAIN_SHUFFLE = True
N_WORKERS = 0
FREEZE_ENCODER = True
LEARNING_RATE = 1e-3
WEIGHT_DECAY = 1e-6
ACCUMULATION_STEPS = 1
EVALUATION_STEPS = 50
USE_SCALER = False
EPOCHS = 10
SAVE_MODEL = True


def get_model(freeze_encoder: bool) -> nn.Module:
    return UNet(
        freeze_encoder=freeze_encoder
    ).to(DEVICE)


def get_criterion() -> nn.Module:
    return nn.BCEWithLogitsLoss()  # TODO: change to KL divergence


def get_optimizer(
    model: nn.Module,
    learning_rate: float,
    weight_decay: float,
) -> nn.Module:
    return torch.optim.Adam(
        model.parameters(),
        lr=learning_rate,
        weight_decay=weight_decay,
    )


def get_trainer(
    model: nn.Module,
    criterion: nn.Module,
    accumulation_steps: int,
    evaluation_steps: int,
    use_scaler: bool,
) -> UNetTrainer:
    return UNetTrainer(
        model=model,
        criterion=criterion,
        accumulation_steps=accumulation_steps,
        evaluation_steps=evaluation_steps,
        use_scaler=use_scaler,
        name=f"unet",
    )


def main() -> None:
    set_seed(SEED)

    # Get dataloaders, model, criterion, optimizer, and trainer
    sample_paths_list = get_sample_paths_list()
    train_loader, val_loader, _ = get_dataloaders(
    sample_paths_list=sample_paths_list,
    sequence_length=SEQUENCE_LENGTH,
    with_transforms=WITH_TRANSFORMS,
    batch_size=BATCH_SIZE,
    train_split=SPLITS[0],
    val_split=SPLITS[1],
    test_split=SPLITS[2],
    train_shuffle=TRAIN_SHUFFLE,
    n_workers=N_WORKERS,
)
    model = get_model(
        freeze_encoder=FREEZE_ENCODER,
    )
    criterion = get_criterion()
    optimizer = get_optimizer(
        model,
        learning_rate=LEARNING_RATE,
        weight_decay=WEIGHT_DECAY,
    )
    trainer = get_trainer(
        model,
        criterion=criterion,
        accumulation_steps=ACCUMULATION_STEPS,
        evaluation_steps=EVALUATION_STEPS,
        use_scaler=USE_SCALER,
    )

    # Train the model
    trainer.train(
        train_loader=train_loader,
        val_loader=val_loader,
        optimizer=optimizer,
        num_epochs=EPOCHS,
        learning_rate=LEARNING_RATE,
        save_model=SAVE_MODEL,
    )


if __name__ == "__main__":
    main()
