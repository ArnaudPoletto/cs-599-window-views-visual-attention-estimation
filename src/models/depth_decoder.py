import torch
from torch import nn

from src.config import IMAGE_SIZE


class DepthDecoder(nn.Module):
    def __init__(
        self, 
        hidden_channels: int,
        dropout_rate: float,
    ) -> None:
        if hidden_channels % 2 != 0:
            raise ValueError("❌ Hidden channels must be divisible by 2.")
        
        super(DepthDecoder, self).__init__()

        self.dropout_rate = dropout_rate

        self.up1 = nn.Sequential(
            nn.ConvTranspose2d(
                hidden_channels,
                hidden_channels // 2,
                kernel_size=3,
                stride=2,
                padding=1,
                output_padding=0,
                bias=False,
            ),
            nn.GroupNorm(num_groups=DepthDecoder._get_num_groups(hidden_channels // 2, 16), num_channels=hidden_channels // 2),
            nn.ReLU(inplace=True),
            nn.Dropout2d(p=dropout_rate),
        )

        # After concatenation with skip connection, input channels double
        self.conv1 = nn.Sequential(
            nn.Conv2d(
                hidden_channels,
                hidden_channels,
                kernel_size=3,
                padding=1,
                bias=False,
            ),
            nn.GroupNorm(num_groups=DepthDecoder._get_num_groups(hidden_channels, 32), num_channels=hidden_channels),
            nn.ReLU(inplace=True),
            nn.Dropout2d(p=dropout_rate),
        )

        self.up2 = nn.Sequential(
            nn.ConvTranspose2d(
                hidden_channels,
                hidden_channels // 2,
                kernel_size=3,
                stride=2,
                padding=1,
                output_padding=1,
                bias=False,
            ),
            nn.GroupNorm(num_groups=DepthDecoder._get_num_groups(hidden_channels // 2, 16), num_channels=hidden_channels // 2),
            nn.ReLU(inplace=True),
            nn.Dropout2d(p=dropout_rate),
        )

        # After concatenation with skip connection, input channels double
        self.conv2 = nn.Sequential(
            nn.Conv2d(
                hidden_channels // 2 + hidden_channels // 4, # TODO: remove hardcoded
                hidden_channels,
                kernel_size=3,
                padding=1,
                bias=False,
            ),
            nn.GroupNorm(num_groups=DepthDecoder._get_num_groups(hidden_channels, 32), num_channels=hidden_channels),
            nn.ReLU(inplace=True),
        )

        self.up3 = nn.Sequential(
            nn.ConvTranspose2d(
                hidden_channels,
                hidden_channels,
                kernel_size=3,
                stride=2,
                padding=1,
                output_padding=0,
                bias=False,
            ),
            nn.GroupNorm(num_groups=DepthDecoder._get_num_groups(hidden_channels, 32), num_channels=hidden_channels),
            nn.ReLU(inplace=True),
        )

    @staticmethod
    def _get_num_groups(num_channels, max_groups):
        num_groups = min(max_groups, num_channels)
        while num_channels % num_groups != 0 and num_groups > 1:
            num_groups -= 1

        return num_groups

    def forward(
        self, x: torch.Tensor, skip_features: list[torch.Tensor]
    ) -> torch.Tensor:
        # Unpack skip features
        skip2, skip1 = skip_features

        # First upsampling + skip connection
        x = self.up1(x)
        x = torch.cat([x, skip2], dim=1)
        x = self.conv1(x)

        # Second upsampling + skip connection
        x = self.up2(x)
        x = torch.cat([x, skip1], dim=1)
        x = self.conv2(x)

        # Final upsampling
        x = self.up3(x)

        return x
