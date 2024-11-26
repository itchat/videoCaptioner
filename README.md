## Intro

This is an open-source project designed to make bilingual video content more accessible.

### Key Features:

1.	Generates English subtitles from videos using the Faster Whisper base model.
2.	Multithreaded Processing: Processes multiple videos simultaneously for fast subtitle generation and translation.
3.	Automatic Translation:
•	Choose between Google Translate or OpenAI for subtitle translation to any target language.
•	Multithreaded translation ensures quick and efficient results.

### Purpose:

This project is designed to help international students better understand educational content by reducing language barriers. 
By providing bilingual subtitles, it ensures that students can follow along more effectively in their native language, enhancing learning and comprehension.

## Compilation

```sh
sudo rm -rf dist build
bash icon_maker.sh translate.svg
sudo pyinstaller main.spec src/main.py
```

Currently only supports build on Apple M series architecture platform

## ToDo

- [ ] Optimize code structure
- [ x ] Internationalize desc
- [ ] Add target language select option
- [ ] Multiple platform support
