$ErrorActionPreference = 'Stop'
$python = if ($env:V3_PYTHON) { $env:V3_PYTHON } else { 'python' }
& $python -m pip install fiftyone albumentations label-studio onnx onnxruntime onnxruntime-gpu mmpose mmdet mmengine mmcv mmaction2
# OpenMMLab packages can be installed separately when GPU/CUDA versions are fixed:
# & $python -m pip install -U openmim
# & $python -m mim install mmengine mmcv mmdet mmpose mmaction2
