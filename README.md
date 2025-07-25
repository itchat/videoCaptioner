## Intro

This is an open-source project designed to make bilingual video content more accessible.

### Key Features:

1.	**Advanced Speech Recognition**: Uses Distil-Whisper `distil-large-v3.5` model for high-accuracy English subtitle generation with 1.5x faster performance.  
2.	**Optimized Multithreaded Processing**: 
    - Thread-safe concurrent processing for multiple videos
    - Smart thread pool management (5 threads for OpenAI, 10 for Google)
    - HTTP session reuse for improved performance
3.	**Intelligent Translation Engine**:  
    - Choose between Google Translate or OpenAI (customizable model, defaults to gpt-4.1) for subtitle translation
    - Batch translation optimization for short subtitles
    - Exponential backoff retry strategy with error tolerance
4.	**Performance Optimizations**:
    - Whisper model caching to avoid repeated loading
    - Thread-safe result collection with accurate progress tracking
    - Robust error handling that doesn't interrupt the entire workflow  

### Purpose:

This project is designed to help international students better understand educational content by reducing language barriers.   
By providing bilingual subtitles, it ensures that students can follow along more effectively in their native language, enhancing learning and comprehension.

## Installation & Setup

### Prerequisites
- macOS (Apple M series recommended)
- Python 3.12+
- ffmpeg installed via Homebrew: `brew install ffmpeg`

### Environment Setup
```sh
# Create conda environment
conda create -n video python=3.13
conda activate video

# Install dependencies
pip install -r requirements.txt
```

### Running the Application
```sh
python src/main.py
```

## Compilation

```sh
bash main.sh
``` 

## ToDo

- [x] Optimize code structure and threading performance
- [x] Test alternative speech recognition models (evaluated [Parakeet TDT 0.6B v2](https://huggingface.co/mlx-community/parakeet-tdt-0.6b-v2) but abandoned due to poor sentence segmentation capabilities)
- [x] Upgrade UI framework from PyQt5 to PyQt6
- [x] Fix handling of silent/no-audio videos (added proper detection and graceful processing)

