
## TODO

1. 目前的核心 bug 是在 main.py 以及大包编译执行 main.sh 后执行 Content/MacOS/main 后，转换视频为 audio 然后识别一切正常，但是一旦用户只是在 dist 目录双击 .app:

- 程序会在提取 .wav audio，进入识别阶段创建 srt 空字幕后就迅速提示 All completed, Desktop 的 log 中也只有这两行：

    ```
    2025-08-04 13:00:37,560 - INFO - Using VideoToolbox hardware acceleration for audio extraction
    2025-08-04 13:00:39,971 - INFO - Audio extraction completed successfully
    ```

    目前已经尝试过了改变路径等，改变多进程调用为 fork forkever 等方式都没用，你想一下其他办法

2. 你应该根据实际任务数量动态调整最大进程数，避免不必要的内存分配，config 中的只是动态调整的最大上限

## Rules

- 全面阅读代码后再进入思考

- 思考完成后先和我说自己的思路，我确认后才能行动

