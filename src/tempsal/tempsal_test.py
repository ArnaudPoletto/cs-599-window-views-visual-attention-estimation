import sys
from pathlib import Path

GLOBAL_DIR = Path(__file__).parent / ".." / ".."
sys.path.append(str(GLOBAL_DIR))

import os
import argparse
import platform
import multiprocessing
import lightning.pytorch as pl

from src.utils.random import set_seed
from src.models.tempsal import TempSAL
from src.utils.parser import get_config
from src.datasets.salicon_dataset import SaliconDataModule
from src.lightning_models.lightning_model import LightningModel
from src.config import (
    SEED,
    N_WORKERS,
    CONFIG_PATH,
    MODELS_PATH,
    CHECKPOINTS_PATH,
    PROCESSED_SALICON_PATH,
)

def _get_data_module(
    batch_size: int,
    train_split: float,
    val_split: float,
    test_split: float,
    use_challenge_split: bool,
    with_transforms: bool,
) -> SaliconDataModule:
    """
    Get the SALICON data module.

    Args:
        batch_size (int): The batch size.
        train_split (float): The train split.
        val_split (float): The validation split.
        test_split (float): The test split.
        with_transforms (bool): Whether to use transforms.

    Returns:
        Any: The data module.
    """
    data_module = SaliconDataModule(
        batch_size=batch_size,
        train_split=train_split,
        val_split=val_split,
        test_split=test_split,
        use_challenge_split=use_challenge_split,
        with_transforms=with_transforms,
        n_workers=N_WORKERS,
        seed=SEED,
    )

    return data_module

def parse_arguments() -> argparse.Namespace:
    """
    Parse command line arguments.

    Returns:
        argparse.Namespace: The parsed arguments.
    """
    parser = argparse.ArgumentParser(description="Process dataset sequences.")

    parser.add_argument(
        "--config-file-path",
        "-config",
        "-conf",
        "-c",
        type=str,
        help="The path to the config file.",
    )

    parser.add_argument(
        "--checkpoint-file-path",
        "-checkpoint",
        "-cp",
        type=str,
        help="The path to the checkpoint file.",
    )

    return parser.parse_args()

def main() -> None:
    if platform.system() != "Windows":
        multiprocessing.set_start_method("forkserver", force=True)
    set_seed(SEED)

    # Parse arguments
    args = parse_arguments()
    config_file_path = args.config_file_path
    checkpoint_file_path = args.checkpoint_file_path

    # Get config parameters
    config = get_config(config_file_path)
    batch_size = int(config["batch_size"])
    splits = tuple(map(float, config["splits"]))
    use_challenge_split = bool(config["use_challenge_split"])
    with_transforms = bool(config["with_transforms"])
    freeze_encoder = bool(config["freeze_encoder"])
    freeze_temporal_pipeline = bool(config["freeze_temporal_pipeline"])
    hidden_channels_list = list(map(int, config["hidden_channels_list"]))
    output_type = str(config["output_type"])
    dropout_rate = float(config["dropout_rate"])
    print(f"✅ Using config file at {Path(config_file_path).resolve()}")

    # Get dataset
    data_module = _get_data_module(
        batch_size=batch_size,
        train_split=splits[0],
        val_split=splits[1],
        test_split=splits[2],
        use_challenge_split=use_challenge_split,
        with_transforms=with_transforms,
    )

    # Get model
    model = TempSAL(
        freeze_encoder=freeze_encoder,
        freeze_temporal_pipeline=freeze_temporal_pipeline,
        hidden_channels_list=hidden_channels_list,
        output_type=output_type,
        dropout_rate=dropout_rate,
    )
    if not os.path.exists(checkpoint_file_path):
        raise FileNotFoundError(
            f"❌ File {Path(checkpoint_file_path).resolve()} not found."
        )
    lightning_model = LightningModel.load_from_checkpoint(
        checkpoint_path=checkpoint_file_path,
        model=model,
        name="tempsal",
        dataset="salicon",
    )
    print(f"✅ Loaded temporal model from {Path(checkpoint_file_path).resolve()}")

    # Get trainer and predict
    trainer = pl.Trainer(
        accelerator="gpu",
        devices=1,
        enable_checkpointing=False,
        logger=False,
    )

    metrics = trainer.test(lightning_model, datamodule=data_module)

    print(f"✅ Test metrics: {metrics}")

if __name__ == "__main__":
    main()