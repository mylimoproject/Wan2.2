"""Model loading and GPU memory management."""
import torch
import os
import sys
from pathlib import Path

MODEL_PATH = None
T5_DEVICE = "cpu"


class ModelManager:
    """Loads Wan2.2 model on specified GPUs with T5 on CPU."""

    def __init__(self, gpu_id, model_path):
        self.gpu_id = gpu_id
        self.model_path = Path(model_path)
        self.device = torch.device("cuda:{}".format(gpu_id))
        self.pipe = None
        self.loaded = False

    def load(self):
        """Load model onto GPU. T5 encoder on CPU."""
        torch.cuda.set_device(self.gpu_id)
        sys.path.insert(0, str(self.model_path.parent.parent))
        from wan.configs import WAN_CONFIGS
        from wan.text2video import WanT2V

        cfg = WAN_CONFIGS.get("t2v-5B", WAN_CONFIGS.get("t2v-A14B"))
        self.pipe = WanT2V(
            config=cfg,
            checkpoint_dir=str(self.model_path),
            device_id=self.gpu_id,
            rank=0,
            t5_cpu=(T5_DEVICE == "cpu"),
        )
        self.loaded = True

    def vram_used_gb(self):
        if not self.loaded:
            return 0.0
        return torch.cuda.memory_allocated(self.gpu_id) / (1024**3)

    def vram_total_gb(self):
        return torch.cuda.get_device_properties(self.gpu_id).total_memory / (1024**3)

    def empty_cache(self):
        torch.cuda.empty_cache()

    def generate(self, prompt, negative_prompt=None, image_path=None,
                 width=1280, height=720, num_frames=97, fps=24,
                 num_inference_steps=50, guidance_scale=5.0, seed=None):
        """Run generation. Returns path to output MP4."""
        torch.cuda.set_device(self.gpu_id)
        import uuid
        from wan.utils.utils import save_video

        kwargs = {
            "prompt": prompt,
            "size": (width, height),
            "frame_num": num_frames,
            "sampling_steps": num_inference_steps,
            "guide_scale": guidance_scale,
        }
        if negative_prompt:
            kwargs["negative_prompt"] = negative_prompt
        if seed is not None:
            kwargs["seed"] = seed

        video = self.pipe.generate(**kwargs)

        output_path = Path.home() / ".local" / "share" / "wan2.2" / "outputs" / "gen-{}.mp4".format(uuid.uuid4())
        output_path.parent.mkdir(parents=True, exist_ok=True)
        save_video(
            tensor=video[None],
            save_file=str(output_path),
            fps=fps,
            nrow=1,
            normalize=True,
            value_range=(-1, 1),
        )
        self.empty_cache()
        return str(output_path)
