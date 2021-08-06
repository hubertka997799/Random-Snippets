# import
import ctypes
from numpy.core.fromnumeric import shape
from pyueye import ueye
import tkinter as tk
from tkinter import Tk, Button, Checkbutton, Text, Label, filedialog, messagebox
from PIL import Image, ImageTk
from argparse import Namespace
from os.path import join, basename
from datetime import datetime
import numpy as np
import subprocess
from ctypes import c_uint, c_wchar_p
import tensorflow as tf


import numpy as np
import math

# choose mamera type here
IS_COLORED_CAMERA = False
if IS_COLORED_CAMERA:
    CAMERA_WIDTH = 2456
    CAMERA_HEIGHT = 2054
else:
    CAMERA_WIDTH = 3088
    CAMERA_HEIGHT = 2076

# class


class IDSCamera:
    def __init__(self, cameraParametersPath):
        # parameters
        self.width = CAMERA_WIDTH  # 2456
        self.height = CAMERA_HEIGHT  # 2054
        if IS_COLORED_CAMERA:
            self.bitspixel = 32  # for colormode = IS_CM_BGRA8_PACKED
        else:
            self.bitspixel = 8
        self.lineinc = self.width * int((self.bitspixel + 7) / 8)

        # init camera
        self.camera = ueye.HIDS(0)
        self.ret = ueye.is_InitCamera(self.camera, None)
        self.check(info='initial')

        # set BGRA8 color mode
        if IS_COLORED_CAMERA:
            self.ret = ueye.is_SetColorMode(self.camera, ueye.IS_CM_BGRA8_PACKED)
        else:
            self.ret = ueye.is_SetColorMode(self.camera, ueye.IS_CM_MONO8)
        self.check(info='set color mode')

        # set region of interest
        rect_aoi = ueye.IS_RECT()
        rect_aoi.s32X = ueye.int(0)
        rect_aoi.s32Y = ueye.int(0)
        rect_aoi.s32Width = ueye.int(self.width)
        rect_aoi.s32Height = ueye.int(self.height)
        ueye.is_AOI(self.camera, ueye.IS_AOI_IMAGE_SET_AOI, rect_aoi, ueye.sizeof(rect_aoi))
        self.check(info='set region of interest')

        # load parameter
        self.ret = ueye.is_ParameterSet(
            self.camera, ueye.IS_PARAMETERSET_CMD_LOAD_FILE, c_wchar_p(cameraParametersPath), c_uint(0))
        self.check(info='load parameter')

        # allocate memory
        self.mem_ptr = ueye.c_mem_p()
        mem_id = ueye.int()
        self.ret = ueye.is_AllocImageMem(
            self.camera, self.width, self.height, self.bitspixel, self.mem_ptr, mem_id)
        self.check(info='allocate memory')

        # set active memory region
        self.ret = ueye.is_SetImageMem(self.camera, self.mem_ptr, mem_id)
        self.check(info='set active memory region')

        # continuous capture to memory
        self.ret = ueye.is_CaptureVideo(self.camera, ueye.IS_DONT_WAIT)
        self.check(info='continuous capture to memory')

        # 鎖定白平衡
        param1 = ctypes.c_double(0)
        ueye.is_SetColorCorrection(self.camera, ueye.IS_CCOR_DISABLE, param1)
        ueye.is_SetAutoParameter(
            self.camera, ueye.IS_SET_ENABLE_AUTO_WHITEBALANCE, param1, param1)
        flagIDS = ueye.is_SetAutoParameter(
            self.camera, ueye.IS_SET_ENABLE_AUTO_SENSOR_WHITEBALANCE, param1, param1)
        qflagIDS = ueye.is_SetHardwareGain(self.camera, 0, 15, 0, 32)

    def check(self, info):
        assert self.ret == 0, 'the camera does not successful {}, the return code {}.'.format(
            info, self.ret)

    def get_image(self):
        image = ueye.get_data(self.mem_ptr, self.width, self.height, self.bitspixel, self.lineinc, copy=True)
        # because the cameraOptimalParameters uses BGRA mode to capture pictures and PIL API uses RGBA mode,
        # then needs to convert to RGBA mode, in addition,  the alpha channel has not any value.
        # So, I select the channel with RGB.
        if IS_COLORED_CAMERA:
            image = np.reshape(image, (self.height, self.width, 4))[:, :, 2::-1]
        else:
            image = np.reshape(image, (self.height, self.width))
        return image

    def release(self):
        self.ret = ueye.is_StopLiveVideo(self.camera, ueye.IS_FORCE_VIDEO_STOP)
        self.check(info='stop live video')
        self.ret = ueye.is_ExitCamera(self.camera)
        self.check(info='exit camera')


class GUI:
    def __init__(self, projectParams):
        self.camera = IDSCamera(cameraParametersPath=projectParams.cameraParametersPath)
        self.projectParams = projectParams
        self.folderPath = None
        camera_width = min(CAMERA_WIDTH, self.projectParams.guiImageSize)
        camera_height = int(camera_width*CAMERA_HEIGHT/CAMERA_WIDTH)
        self.projectParams.guiImageSize = [camera_height, camera_width]

        # window
        self.window = Tk()
        self.window.geometry('{}x{}'.format(
            self.window.winfo_screenwidth(), self.window.winfo_screenheight()))
        self.window.title('IDS Camera GUI')

        # tkinter variable
        self.uploadBooleanVar = tk.BooleanVar()

        # button
        self.imageFolderPathButton = Button(
            self.window, text='影像存放位置', fg='black', bg='white', command=self.browse_folder)
        self.shootButton = Button(
            self.window, text='拍照', fg='black', bg='white', command=self.take_picture)
        self.setBackgroundButton = Button(
            self.window, text='背景設定', fg='black', bg='white', command=self.set_background)
        self.autoShootButton = Button(
            self.window, text='自動拍照', fg='black', bg='white', command=self.auto_shoot)
        # checkbutton
        self.uploadCheckbutton = Checkbutton(
            self.window, text='拍照並自動上傳', fg='black', variable=self.uploadBooleanVar, onvalue=True, offvalue=False)

        # label
        self.sampleNameLabel = Label(self.window, text='樣本名稱', fg='black')
        self.galleryTextLabel = Label(self.window, text='即時影像', fg='black')
        self.galleryImageLabel = Label(self.window, text='', fg='black')
        self.imagePathLabel = Label(self.window, text='', fg='black')

        # text
        self.sampleNameText = Text(self.window, height=2, width=10)

        # auto_shoot
        self.do_auto_shoot = False
        self.n = 30  # continuous picture
        self.continuous_psnr = 0
        self.moving_backup = False
        self.moving = False
        self.background = self.camera.get_image()

    def browse_folder(self):
        self.folderPath = filedialog.askdirectory(initialdir='./')

    def upload_image(self, filepath):
        subprocess.run(
            ['scp', filepath, '{}@{}:{}'.format(
                self.projectParams.user, self.projectParams.ip,
                join(self.projectParams.targetPath, basename(filepath)))])

    def take_picture(self):
        if self.folderPath is None:
            messagebox.showinfo(title='錯誤', message='尚未選取影像存放位置！')
        else:
            filename = join('{}_{}.png'.format(
                self.sampleNameText.get('1.0', 'end-1c'), datetime.now().strftime('%Y%m%d%H%M%S%f')))
            self.image.save(join(self.folderPath, filename))
            self.imagePathLabel.config(
                text='影像位置: {}'.format(join(self.folderPath, filename)))
            if self.uploadBooleanVar.get():
                self.upload_image(filepath=join(self.folderPath, filename))

    def set_background(self):
        self.background = self.camera.get_image()
        print("set")

    def auto_shoot(self):
        self.do_auto_shoot = not self.do_auto_shoot
        if self.do_auto_shoot:
            print("dadada")

    def psnr(self, img1, img2):
        mse = np.mean((img1/255. - img2/255.) ** 2)
        if mse < 1.0e-10:
            return 100
        PIXEL_MAX = 1
        return 20 * math.log10(PIXEL_MAX / math.sqrt(mse))

    def get_realtime_image(self):
        # the self.camera.get_image() will return RGB image array
        if IS_COLORED_CAMERA:
            self.image = Image.fromarray(self.camera.get_image(), mode='RGB')
        else:
            self.image = Image.fromarray(self.camera.get_image())
        self.imageTk = ImageTk.PhotoImage(self.image.resize(
            self.projectParams.guiImageSize))  # resize the image
        self.galleryImageLabel.config(image=self.imageTk)
        # insert auto shoot here
        self.image_first = self.camera.get_image()
        if self.do_auto_shoot == True:
            psnr = self.psnr(self.image_first, self.image_backup)
            if psnr > 38:
                self.continuous_psnr = self.continuous_psnr+1
            else:
                self.continuous_psnr = 0
                self.moving = True
        if self.continuous_psnr > self.n:
            if self.moving == True:
                self.moving = False
                bg_psnr = self.psnr(self.background, self.image_first)
                if bg_psnr < 30:
                    print(bg_psnr, "shoot")
                    self.take_picture()
        self.image_backup = self.image_first

        self.galleryImageLabel.image = self.imageTk
        self.galleryImageLabel.after(1, self.get_realtime_image)

    def run(self):

        # position, 1st column
        self.imageFolderPathButton.pack(anchor=tk.NW)
        self.sampleNameLabel.pack(anchor=tk.NW)
        self.sampleNameText.pack(anchor=tk.NW)
        self.shootButton.pack(anchor=tk.NW)
        self.setBackgroundButton.pack(anchor=tk.NW)
        self.autoShootButton.pack(anchor=tk.NW)
        self.uploadCheckbutton.pack(anchor=tk.NW)

        # position, 2nd column
        self.galleryTextLabel.pack(anchor=tk.N)
        self.galleryImageLabel.pack(anchor=tk.N)
        self.imagePathLabel.pack(anchor=tk.N)

        # run
        self.get_realtime_image()
        self.window.mainloop()
        self.camera.release()


if __name__ == '__main__':
    # parameters
    projectParams = Namespace(**{'guiImageSize': 1000,  # set maximum width
                                 # /home/iris/hubertka/camera/toolkit/Python/1223.ini', #colored
                                 'cameraParametersPath': '/home/iris/hubertka/0721研磨片/0721.ini',
                                 'ip': '',
                                 'user': '',
                                 'targetPath': '~/Desktop/temp'})

    # GUI
    gui = GUI(projectParams=projectParams)
    gui.run()
