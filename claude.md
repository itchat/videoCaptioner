
## TODO

1. 目前 ffmpeg 烧录字幕进视频的过程有些无意义，我在想能否在设置中增加一个设置按钮，用户可以决定是否需要最后一步
2. 目前原字幕与双语字幕在 cache 文件夹中，改到视频原目录中
3. 目前视频添加到拖动方框后，再拖动新的一些视频会直接替代原有视频列表，原视频列表直接消失，我们已经有 clear history 按钮不应该消失，应该添加新的视频在 queue，除非重复那么只添加新视频在 queue
4. 软件过程中有这个 warning:

```
"2025-08-04 15:09:24,647 - WARNING - Could not check audio streams: Command '['/Users/ronin/Desktop/videoCaptioner/dist/videoCaptioner.app/Contents/Frameworks/ffmpeg', '-i', '/Users/ronin/Downloads/CITS3200_Lecture_Jak-s1-full.mp4', '-hide_banner', '-f', 'null', '-']' timed out after 30 seconds
2025-08-04 15:09:24,647 - WARNING - Could not check audio streams: Command '['/Users/ronin/Desktop/videoCaptioner/dist/videoCaptioner.app/Contents/Frameworks/ffmpeg', '-i', '/Users/ronin/Downloads/CITS3200 - 30 Jul 20-s1-full.mp4', '-hide_banner', '-f', 'null', '-']' timed out after 30 seconds"
```

## Rules

- 全面阅读代码后再进入思考

<!-- - 思考完成后先和我说自己的思路，我确认后才能行动 -->

- 用最精简核心的方法修改 bug，不要擅自创建冗余测试以及其他加固

- 我自己会测试
