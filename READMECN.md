<a href="./README.md"><img src="https://img.shields.io/badge/🇬🇧English-e9e9e9" width="100"></a>
<a href="./READMECN.md"><img src="https://img.shields.io/badge/🇨🇳中文简体-0b8cf5" width="100"></a>
# Blender AI Studio

它是一款用于**全面增强Blender AI使用体验**的Addon，以下是它的特征

· 支持使用Nano Banana Pro等图像模型，将Grease pencil、3d场景等通过相机输出后，进行加工/优化，生成**海报、概念设计图、电影分镜、漫画、设定图等....**

· 支持**1/2/4K**分辨率，以及非Google支持地区使用

· 支持**图像修复**，**图像编辑**

· 支持**任务队列**&**历史记录**

· 支持**更好的UI交互**————它是用来展示[Addon UI-Forge](https://github.com/AIGODLIKE/AddonUI-Forge)(下一代Blender Addon UI框架)的示范工程

<img width="425" height="343" alt="AddonUIForgeCN" src="https://github.com/user-attachments/assets/2c689bc5-3865-4102-aa77-c4af3edabca1" />

## 用户界面——[Addon UI-Forge](https://github.com/AIGODLIKE/AddonUI-Forge)概念版

<img width="1280" height="690" alt="image" src="https://github.com/user-attachments/assets/f11f92b0-d5a6-48c1-a1f2-0b52df51ac65" />

## 







## 工具安装

1.在[Releases](https://github.com/AIGODLIKE/BlenderAIStudio/releases)下载最新的`.zip`,并打开Blender，依次找到编辑->偏好设置->插件->从磁盘安装

<img width="1920" height="1033" alt="image" src="https://github.com/user-attachments/assets/bc8e034a-c978-45f9-b65a-a572a9e5ebbf" />

2.选中压缩包，点击安装插件

<img width="1920" height="1036" alt="image" src="https://github.com/user-attachments/assets/3763ff39-ebb1-4f6c-b476-f54ed3e4a1e2" />

3.安装完成，可以看到插件目录与面板上出现新的按钮

<img width="1920" height="1038" alt="image" src="https://github.com/user-attachments/assets/7f12519a-d873-4e72-9b3d-b11dcb5eea7f" />

4.第一次运行，可能需要重启一次Blender

## 初始化设置

### 界面设置

由于ADDON UI FORGE的自适应缩放还未开发就绪，如果遇到界面过大/过小，请在插件设置里手动调整

<img width="1920" height="1036" alt="image" src="https://github.com/user-attachments/assets/dc9dd4cf-7479-42e0-9c3e-9873f562fe5a" />

### 缓存/输出设置

无限之心AI（BlenderAIStudio）为了确保您生成的内容不会消失，特别是意外关闭未保存工程，在这里提供了一个支持自定义的缓存文件夹，任何生成成功的内容都会放置于此处

<img width="1920" height="1035" alt="image" src="https://github.com/user-attachments/assets/c8803767-8216-43ee-813d-12892eccde6e" />

### 填写API

1.在设置中找到服务设置，然后切换到API模式

<img width="473" height="907" alt="image" src="https://github.com/user-attachments/assets/5ece0bcc-9d1e-458c-9e24-d4aa07bd64bf" />

2.到[Google AI Studio](https://aistudio.google.com/)中创建API

<img width="374" height="892" alt="image" src="https://github.com/user-attachments/assets/77938f55-4805-4f11-a588-617992a88184" />

3.一切就绪，尽情使用吧

### 参考项目

[nano-banana-render](https://github.com/Kovname/nano-banana-render)
