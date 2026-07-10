from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
from torch import nn
from torch.utils.data import DataLoader
from torchvision import datasets, transforms

ARTIFACT_DIR = Path("/mnt/artifacts")


class SmallCNN(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv2d(1, 16, 3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2),
            nn.Conv2d(16, 32, 3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2),
            nn.Flatten(),
            nn.Linear(32 * 7 * 7, 64),
            nn.ReLU(),
            nn.Linear(64, 10),
        )

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        return self.net(inputs)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train a small CNN on MNIST.")
    parser.add_argument("--epochs", type=int, default=1, choices=(1, 2, 3))
    parser.add_argument("--batch-size", type=int, default=128)
    return parser.parse_args()


def evaluate(model: nn.Module, loader: DataLoader, device: torch.device) -> tuple[float, float]:
    model.eval()
    loss_fn = nn.CrossEntropyLoss(reduction="sum")
    total_loss = 0.0
    correct = 0
    total = 0
    with torch.no_grad():
        for images, labels in loader:
            images = images.to(device)
            labels = labels.to(device)
            outputs = model(images)
            total_loss += float(loss_fn(outputs, labels).item())
            correct += int((outputs.argmax(dim=1) == labels).sum().item())
            total += int(labels.numel())
    return total_loss / total, correct / total


def main() -> None:
    args = parse_args()
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    is_cuda_available = torch.cuda.is_available()
    device = torch.device("cuda" if is_cuda_available else "cpu")
    device_name = torch.cuda.get_device_name(0) if is_cuda_available else "cpu"
    print(f"torch cuda available: {is_cuda_available}", flush=True)
    print(f"device: {device_name}", flush=True)

    transform = transforms.Compose(
        [transforms.ToTensor(), transforms.Normalize((0.1307,), (0.3081,))]
    )
    data_dir = ARTIFACT_DIR / "data"
    train_data = datasets.MNIST(data_dir, train=True, download=True, transform=transform)
    test_data = datasets.MNIST(data_dir, train=False, download=True, transform=transform)
    train_loader = DataLoader(train_data, batch_size=args.batch_size, shuffle=True, num_workers=2)
    test_loader = DataLoader(test_data, batch_size=512, shuffle=False, num_workers=2)

    model = SmallCNN().to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    loss_fn = nn.CrossEntropyLoss()

    last_train_loss = 0.0
    for epoch in range(1, args.epochs + 1):
        model.train()
        running_loss = 0.0
        sample_count = 0
        for images, labels in train_loader:
            images = images.to(device)
            labels = labels.to(device)
            optimizer.zero_grad(set_to_none=True)
            outputs = model(images)
            loss = loss_fn(outputs, labels)
            loss.backward()
            optimizer.step()
            running_loss += float(loss.item()) * int(labels.numel())
            sample_count += int(labels.numel())
        last_train_loss = running_loss / sample_count
        val_loss, val_accuracy = evaluate(model, test_loader, device)
        print(
            f"epoch {epoch}/{args.epochs} train_loss={last_train_loss:.4f} "
            f"val_loss={val_loss:.4f} val_accuracy={val_accuracy:.4f}",
            flush=True,
        )

    checkpoint_path = ARTIFACT_DIR / "mnist-cnn.pt"
    metrics_path = ARTIFACT_DIR / "mnist-metrics.json"
    torch.save(model.state_dict(), checkpoint_path)
    metrics = {
        "epochs": args.epochs,
        "device": str(device),
        "device_name": device_name,
        "train_loss": last_train_loss,
        "checkpoint": str(checkpoint_path),
    }
    metrics_path.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    print(f"saved checkpoint: {checkpoint_path}", flush=True)
    print(f"saved metrics: {metrics_path}", flush=True)


if __name__ == "__main__":
    main()
