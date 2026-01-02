
<a href="./README.md"><img src="https://img.shields.io/badge/🇬🇧English-0b8cf5"  width="100"></a>
<a href="./READMECN.md"><img src="https://img.shields.io/badge/🇨🇳中文简体-e9e9e9" width="100"></a>

# Blender AI Studio

An addon to **fully enhance Blender's AI workflow**, serving as a demonstration for [Addon UI-Forge](https://github.com/AIGODLIKE/AddonUI-Forge) (next-gen Blender Addon UI framework).

Note: This is not an official Blender project.


## Key Features

- Supports models like Nano Banana Pro: Process Grease Pencil/3D scenes (via camera output) into posters, concept art, storyboards, comics, and design sheets.

- Resolution support: 1K/2K/4K; Works in non-Google supported regions.

- Core capabilities: Image inpainting, image editing, task queuing, and history records.

- Enhanced UI: Powered by [Addon UI-Forge](https://github.com/AIGODLIKE/AddonUI-Forge) for intuitive interaction.

<img width="425" height="343" alt="ADDON UI Forge" src="https://github.com/user-attachments/assets/b854c434-9780-44d7-b1b3-8aee240e8983" />


## UI Preview (Addon UI-Forge Concept)

<img width="1280" height="690" alt="image" src="https://github.com/user-attachments/assets/f11f92b0-d5a6-48c1-a1f2-0b52df51ac65" />

## Core Functions

|Function|Description|
|---|---|
|Engine|Select supported AI generation engines.|
|Input Image (Primary)|Supports rendered images, depth maps, or text-to-image (no input). Serves as the first image in the queue (called "rendered/original image").|
|Prompt|Describe desired (or unwanted) content for generation.|
|Prompt Optimization|Enabled by default; Marks the first image as "rendered/original" and others as references.|
|Reference Images|Up to 10 images; Aids in refining effects and compositional elements.|
|Dimension Settings|Adaptive (matches render output ratio) or fixed (forces specified ratio).|
|Resolution|2K recommended (best cost-performance). 4K may cause blurring and higher costs; Upscale manually for better results.|
## Usage Demos

### Camera Render Mode

Uses camera-rendered content as the primary input (rendered/original image).

#### 01 Model-Scene Matching

|Rendered/Original|Prompt|Output|
|---|---|---|
|<img width="1848" height="1035" alt="image" src="https://github.com/user-attachments/assets/1f56a53e-5077-47fc-88c3-8a0e8259b1d0" />|E-commerce poster: ACGGit tablet on beige stones, surrounded by flowers, floating blurred blooms, realistic photo, ultra-detailed, professional photography, dramatic lighting, 8K|<img width="1506" height="839" alt="image" src="https://github.com/user-attachments/assets/ebd1964b-09b9-420f-b403-51e7626ef591" />|
#### 02 Scene Model Replacement

|Rendered/Original|Prompt|Reference|Output|
|---|---|---|---|
|<img width="1848" height="1035" alt="image" src="https://github.com/user-attachments/assets/1f56a53e-5077-47fc-88c3-8a0e8259b1d0" />|Replace the product in the reference scene with the tablet from the rendered image|<img width="852" height="1187" alt="image" src="https://github.com/user-attachments/assets/565c94b3-fdbc-43cd-9d0f-f95176d76253" />|<img width="1507" height="842" alt="image" src="https://github.com/user-attachments/assets/ec0cdd49-3fe7-4bc8-8359-24c80d21bd3d" />|
#### 03 Style Conversion

|Rendered/Original|Prompt|Output|
|---|---|---|
|<img width="587" height="1042" alt="image" src="https://github.com/user-attachments/assets/b34885ba-5d38-49b9-93fa-e28165390c4b" />|2D poster: Earth surface background (clouds, oceans, planes, spaceships), anime style|<img width="574" height="1041" alt="image" src="https://github.com/user-attachments/assets/53da8a81-9129-4f9b-8c9b-252dc595456f" />|
#### 04 Sketch to Storyboard

|Rendered/Original|Prompt|Reference|Output|
|---|---|---|---|
|<img width="2252" height="947" alt="image" src="https://github.com/user-attachments/assets/2ec15c66-65a8-4da0-b9d9-6ccdb8509bf8" />|Preserve ratio/composition/shot; Refine storyboard sketch: Giant robot pilot (combat suit, glass helmet, surprised expression), 2D style (reference character in reference image)|<img width="574" height="1031" alt="image" src="https://github.com/user-attachments/assets/1526b46c-5c5f-47a9-bda2-97569166898d" />|<img width="1738" height="742" alt="image" src="https://github.com/user-attachments/assets/71d52540-65df-4b69-8647-c12f99783461" />|


### Depth Render Mode

Blurs details to avoid limiting AI imagination (vs. standard render mode).

#### Fog Scene Generation

|Depth Map|Prompt|Output|
|---|---|---|
|<img width="1847" height="1034" alt="image" src="https://github.com/user-attachments/assets/d49c0fdd-e257-4631-bf31-da05e058b900" />|Realistic 3D town street scene (game-ready), no characters|<img width="1509" height="835" alt="image" src="https://github.com/user-attachments/assets/d7a63c4c-fe04-47a7-abb6-3af3d540e62b" />|
### Text-to-Image Mode (No Input)

|Prompt|Output|
|---|---|
|Anime illustration: Blue-haired boy & blonde cat-eared girl (playful dynamic), laughing expressions, cyberpunk neon (pink/blue/yellow outlines), high saturation, black background, sharp lines, vibrant atmosphere|<img width="896" height="1200" alt="image" src="https://github.com/user-attachments/assets/1358486b-0022-4e18-8a5a-61d3fbcde790" />|
## Installation

1. Download the latest `.zip` from [Releases](https://github.com/AIGODLIKE/BlenderAIStudio/releases).Open Blender →**Edit** → **Preferences** → **Add-ons** → **Install from Disk**.

<img width="2560" height="1380" alt="image" src="https://github.com/user-attachments/assets/70240e61-4821-46c5-bf3c-4189f8fabacd" />

2. Select the downloaded zip file and click Install Add-on.

<img width="2554" height="1378" alt="image" src="https://github.com/user-attachments/assets/d7b1ba7f-ca43-4164-9b80-a8db59687b96" />


3. After installation is complete, you will see new buttons appear in the add-on list and panel.

<img width="2560" height="1380" alt="image" src="https://github.com/user-attachments/assets/ee88e753-ce3d-402d-9fa6-d9cc726163cb" />


4. Verify: New buttons appear in the add-on list/panel. Restart Blender if needed (first run).



## Initial Setup

### Interface Adjustment

Adaptive scaling for Addon UI-Forge is in progress. Manually adjust the interface size in add-on settings if it’s too large/small.

<img width="2560" height="1380" alt="image" src="https://github.com/user-attachments/assets/bffd0b13-3ced-4e2e-829a-10afca5a4d2b" />

### Cache/Output Settings

Blender AI Studio saves all generated content to a customizable cache folder to prevent data loss (e.g., accidental Blender closure).
<img width="2557" height="1379" alt="image" src="https://github.com/user-attachments/assets/02768078-2f01-4490-b5a5-f3312646f360" />

### API Configuration

1. Go to **Service Settings** → Switch to**API Mode**.
<img width="355" height="885" alt="image" src="https://github.com/user-attachments/assets/3b12f5e0-613c-483e-9980-7dd786779b46" />

2. Create an API key at [Google AI Studio](https://aistudio.google.com/).
3. Complete! Start using the addon.
<img width="354" height="892" alt="image" src="https://github.com/user-attachments/assets/a447b34a-b731-4f1a-9f5d-26aa8ee75d31" />

## Credits

Inspired by [nano-banana-render](https://github.com/Kovname/nano-banana-render) during development.

