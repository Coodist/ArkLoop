from abc import ABC, abstractmethod
from PIL import Image


class BaseCaptureController(ABC):
    """Abstract base class for all capture controllers."""

    @abstractmethod
    def connect(self):
        """Establish connection and initialize."""
        return self

    @abstractmethod
    def disconnect(self):
        """Disconnect and clean up all resources."""
        pass

    @abstractmethod
    def capture_frame(self) -> Image.Image:
        """Capture a single frame."""
        pass

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
