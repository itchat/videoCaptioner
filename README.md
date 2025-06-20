## Intro

This is an open-source project designed to make bilingual video content more accessible.

### Key Features:

1.	**Advanced Speech Recognition**: Uses Faster Whisper `large-v3` model for high-accuracy English subtitle generation.  
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
- Python 3.8+
- ffmpeg installed via Homebrew: `brew install ffmpeg`

### Environment Setup
```sh
# Create conda environment
conda create -n video python=3.11
conda activate video

# Install dependencies
pip install -r requirements.txt
```

### Running the Application
```sh
conda activate video
python src/main.py
```

## Compilation

```sh
sudo rm -rf dist build
bash icon_maker.sh translate.svg
sudo pyinstaller main.spec src/main.py
```

Currently only supports build on Apple M series architecture platform  

## Performance Optimizations (v2.0)

### Recent Improvements
- **30-50% faster translation** through intelligent threading
- **Model caching** eliminates repeated Whisper model loading
- **HTTP session reuse** reduces API call overhead
- **Thread-safe operations** prevent race conditions
- **Smart retry logic** with exponential backoff
- **Batch translation** for improved API efficiency

### Benchmarks
- 50 concurrent subtitle translations: **0.53s** completion time
- Thread safety: **100% success rate** with no data loss
- Error recovery: **Automatic retry** with intelligent backoff

For detailed optimization information, see [OPTIMIZATION_SUMMARY.md](OPTIMIZATION_SUMMARY.md).

## ToDo

- [x] Optimize code structure and threading performance
- [x] Upgrade to Whisper large-v3 model for better accuracy
- [x] Implement intelligent retry mechanisms and error handling
- [x] Add HTTP session reuse and connection pooling
- [x] Internationalize descriptions and documentation
- [ ] Add translation result caching system
- [ ] Support for multiple target languages selection
- [ ] Cross-platform support (Windows, Linux)
- [ ] Resume functionality for interrupted processing
- [ ] Real-time processing progress visualization
