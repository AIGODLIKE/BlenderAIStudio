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

## 基本功能

|功能名|描述|
|:----|:----|
|引擎|选择支持的生成引擎|
|输入图（首图）|可选择输入渲染、深度图像或不输入图像(文生图)，如选择输入，则该图像为队列第一张图像，同时它的名字被称为**渲染图**或**原图**|
|提示词|描述所需要生成的内容（不想要的也可以写）|
|提示词优化|默认开启，用于定义第一张图为渲染图/原图，其它为参考图|
|参考图|最多支持10张，可辅助生成效果/构成元素|
|尺寸设置|自适应=根据当前渲染输出比例匹配分辨率其它=强制输出规定比例匹配分辨率|
|分辨率|生成图像的分辨率，分辨率越大，生成时间越长。推荐2K分辨率，性价比高。4K容易产生涂抹还贵，不如自己放大。|

## 使用示范

### 相机渲染模式

直接输出相机渲染内容，用作第一张输入图，此图像被称为渲染图/原图

#### 01为模型匹配场景

|渲染图/原图|提示词|输出图像|
|:----|:----|:----|
|<img width="1848" height="1035" alt="image" src="https://github.com/user-attachments/assets/1f56a53e-5077-47fc-88c3-8a0e8259b1d0" />|电商海报，米色石头上有一台参考图的平板电脑产品，品牌ACGGit，周围花花卉拥着，背景漂浮着很多模糊朦胧的花朵，真实的照片，极致的清晰度和细节，大师级摄影，强烈的光影，8k画质|<img width="1506" height="839" alt="image" src="https://github.com/user-attachments/assets/ebd1964b-09b9-420f-b403-51e7626ef591" />|

#### 02替换场景中模型

|渲染图/原图|提示词|参考图|输出图像|
|:----|:----|:----|:----|
|<img width="1848" height="1035" alt="image" src="https://github.com/user-attachments/assets/1f56a53e-5077-47fc-88c3-8a0e8259b1d0" />|将参考图场景中的产品，换成渲染图的平板电脑|<img width="852" height="1187" alt="image" src="https://github.com/user-attachments/assets/565c94b3-fdbc-43cd-9d0f-f95176d76253" />|<img width="1507" height="842" alt="image" src="https://github.com/user-attachments/assets/ec0cdd49-3fe7-4bc8-8359-24c80d21bd3d" />|

#### 03渲染风格转换
|渲染图/原图|提示词|输出图像|
|:----|:----|:----|
|<img width="587" height="1042" alt="image" src="https://github.com/user-attachments/assets/b34885ba-5d38-49b9-93fa-e28165390c4b" />|渲染2D风格海报，背景为地球地面，可以看到云和海洋，飞机，宇宙飞船。动漫风格|<img width="574" height="1041" alt="image" src="https://github.com/user-attachments/assets/53da8a81-9129-4f9b-8c9b-252dc595456f" />|

#### 04草图转分镜
|渲染图/原图|提示词|参考图|输出图像|
|:----|:----|:----|:----|
|<img width="2252" height="947" alt="image" src="https://github.com/user-attachments/assets/2ec15c66-65a8-4da0-b9d9-6ccdb8509bf8" />|保持渲染图比例/构图/镜头不变，渲染图是一张分镜草图，请完善细节，一个巨型机器人驾驶员，穿着战斗服装，头戴玻璃头盔，凝视着镜头，漏出吃惊的表情。风格为2D风格，参考图角色|<img width="574" height="1031" alt="image" src="https://github.com/user-attachments/assets/1526b46c-5c5f-47a9-bda2-97569166898d" />|<img width="1738" height="742" alt="image" src="https://github.com/user-attachments/assets/71d52540-65df-4b69-8647-c12f99783461" />|


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
