## Intro

This is an open-source project designed to make bilingual video content more accessible.

### Key Features:

1.	**Advanced Speech Recognition**: Uses MLX-optimized Parakeet `parakeet-tdt-0.6b-v2` model for high-accuracy multilingual subtitle generation with significantly improved precision and 2x faster performance compared to previous models.
2.	**Optimized Multithreaded Processing**: 
    - Thread-safe concurrent processing for multiple videos
    - HTTP session reuse for improved performance
3.	**Intelligent Translation Engine**:  
    - Choose between Google Translate or OpenAI (customizable model, defaults to gpt-4o) for subtitle translation
    - **Revolutionary Batch Translation**: Inspired by immersive translation techniques, optimized SRT subtitle batch processing reduces API calls from thousands to single digits, dramatically improving translation speed and reducing costs
    - **New Paragraph Separator Translation System**: Replaces fragile JSON-based translation with robust %% separator format, eliminating parsing errors and improving reliability
    - Smart batch sizing (1200 chars/4 entries max) optimized for translation quality
    - Exponential backoff retry strategy with error tolerance
4.	**Performance Optimizations**:
    - MLX framework acceleration for Apple Silicon
    - Parakeet model caching to avoid repeated loading
    - Thread-safe result collection with accurate progress tracking
    - **Enhanced Progress Monitoring**: Fine-grained progress bars with real-time status updates and precise percentage tracking across all processing stages
    - Robust error handling that doesn't interrupt the entire workflow
    - Streamlined codebase with redundant code removal and manual code review

### Purpose:

This project is designed to help international students better understand educational content by reducing language barriers.   
By providing bilingual subtitles, it ensures that students can follow along more effectively in their native language, enhancing learning and comprehension.

## Installation & Setup

### Prerequisites
- macOS (Apple Silicon M1/M2/M3 recommended for MLX acceleration)
- Python 3.13+
- ffmpeg installed via Homebrew: `brew install ffmpeg`

### Environment Setup
```sh
# Create conda environment
conda create -n video python=3.13
conda activate video

# Install dependencies (includes MLX framework for Apple Silicon optimization)
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

## Recent Updates (Latest Version)

### 🚀 Major Performance & Accuracy Improvements

**Speech Recognition Revolution:**
- **Complete migration to Parakeet TDT 0.6B v2**: Leveraging MLX framework optimization for Apple Silicon
- **2x faster processing** with significantly improved recognition accuracy
- **Native Apple Silicon acceleration** through MLX framework integration

**Translation Breakthrough:**
- **Batch Translation Optimization**: Analyzed and implemented immersive translation methodology for SRT subtitle processing
- **API Call Reduction**: Optimized from thousands of individual requests to single-digit batch calls  
- **New Paragraph Separator System**: Replaced JSON-based translation with %% separator format, eliminating parsing errors
- **Smart Batch Processing**: Customizable batch parameters (default: 1200 chars/4 entries) with user-configurable limits optimized for translation quality and reliability
- **Cost & Speed**: Dramatically reduced translation costs and processing time

**Code Quality & Maintenance:**
- **Comprehensive code cleanup**: Removed redundant code and legacy implementations
- **Manual code review**: Improved code maintainability and performance
- **Streamlined architecture**: More efficient and cleaner codebase

**UI/UX Improvements:**
- **Enhanced API Settings Dialog**: Improved user interface with cleaner SpinBox controls (removed increment/decrement buttons)
- **Complete Reset Functionality**: Reset button now properly restores all settings including Base URL and Model to defaults
- **Advanced Input Validation**: Enhanced form validation with detailed error messages for empty fields
- **Optimized Layout**: Adjusted dialog proportions for better visual balance with new batch processing controls

## ToDo

- [x] Optimize code structure and threading performance
- [x] **Major Update**: Upgrade speech recognition to Parakeet TDT 0.6B v2 with MLX optimization - dramatically improved accuracy and 2x speed increase
- [x] **Revolutionary Translation Optimization**: Implement batch translation inspired by immersive translation techniques, reducing API calls from thousands to single digits
- [x] **Translation System v2.0**: Complete overhaul with paragraph separator format (%%) replacing JSON-based approach, eliminating parsing errors and improving reliability through competitor-inspired optimization
- [x] Upgrade UI framework from PyQt5 to PyQt6
- [x] Fix handling of silent/no-audio videos (added proper detection and graceful processing)
- [x] **Code Quality**: Comprehensive code cleanup - removed redundant code and conducted manual code review for improved maintainability
- [x] **Enhanced Progress Tracking**: Implemented fine-grained progress bars with real-time status updates and precise percentage tracking for better user experience

