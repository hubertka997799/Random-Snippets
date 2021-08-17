'''
https://cn.ids-imaging.com/manuals/ids-software-suite/ueye-manual/4.94/zh/is_camerastatus.html
'''

# import
import ctypes
from src.project_parameters import ProjectParameters
from src.predict import Predict
import configparser
from ctypes import c_uint, c_wchar_p
import numpy as np
from os.path import join
from pyueye import ueye
from tkinter import Tk, Button, filedialog, messagebox, Label, Text
from datetime import datetime
from PIL import Image, ImageTk
import tkinter as tk
import cv2
from time import sleep, time
from multiprocessing import Process
from threading import Thread

# class


class IDSCAMERA:
    def __init__(self, camera_parameter_path):
        # table
        self.color_modes_table = {'6': 'ueye.IS_CM_MONO8',
                                  '0': 'ueye.IS_CM_BGRA8_PACKED',
                                  '1': 'ueye.IS_CM_BGR8_PACKED'}
        self.bits_of_pixel_table = {'6': 8,
                                    '0': 32,
                                    '1': 24}
        self.color_code_table = {'BGR': cv2.COLOR_BGR2RGB,
                                 'BGRA': cv2.COLOR_BGRA2RGB}

        # parameters
        self.config = self._load_ini_file(
            camera_parameter_path=camera_parameter_path)
        self.width = int(self.config['Image size']['Width'])
        self.height = int(self.config['Image size']['Height'])
        self.bitspixel = self.bits_of_pixel_table[self.config['Parameters']['Colormode']]
        self.lineinc = self.width * int((self.bitspixel + 7) / 8)
        self.channels = int(np.ceil((self.bitspixel/8)))
        self.color_mode = self.color_modes_table[self.config['Parameters']['Colormode']]
        self.color_order = ''.join(filter(lambda x: not x.isdigit(
        ), self.color_mode.split('IS_CM_')[1].split('_')[0]))
        self.color_code = self.color_code_table.get(self.color_order)

        # init camera
        self.camera = ueye.HIDS(0)
        result = ueye.is_InitCamera(phCam=self.camera, hWnd=None)
        self._check(result=result, info='initial')

        # set color mode
        result = ueye.is_SetColorMode(
            hCam=self.camera, Mode=eval(self.color_mode))
        self._check(result=result, info='set color mode')

        # load parameter
        result = ueye.is_ParameterSet(hCam=self.camera, nCommand=ueye.IS_PARAMETERSET_CMD_LOAD_FILE, pParam=c_wchar_p(
            camera_parameter_path), cbSizeOfParam=c_uint(0))
        self._check(result=result, info='load parameter')

        # allocate memory
        self.mem_ptr = ueye.c_mem_p()
        mem_id = ueye.int()
        result = ueye.is_AllocImageMem(hCam=self.camera, width=self.width, height=self.height,
                                       bitspixel=self.bitspixel, ppcImgMem=self.mem_ptr, pid=mem_id)
        self._check(result=result, info='allocate memory')

        # set active memory region
        result = ueye.is_SetImageMem(
            hCam=self.camera, pcMem=self.mem_ptr, id=mem_id)
        self._check(result=result, info='set active memory region')

        # set DIB
        result = ueye.is_SetDisplayMode(
            hCam=self.camera, Mode=ueye.IS_SET_DM_DIB)
        self._check(result=result, info='set DIB')

        self._start_image_queue()

    def _load_ini_file(self, camera_parameter_path):
        config = configparser.ConfigParser()
        config.read(camera_parameter_path, 'utf-8-sig')
        return config

    def _check(self, result, info):
        assert result == ueye.IS_SUCCESS, 'the camera does not successful {}, the return code {}.'.format(
            info, result)

    def __call__(self):
        result = ueye.is_FreezeVideo(hCam=self.camera, Wait=ueye.IS_WAIT)
        self._check(result=result, info='freeze video')
        image = ueye.get_data(image_mem=self.mem_ptr, x=self.width, y=self.height,
                              bits=self.bitspixel, pitch=self.lineinc, copy=False)
        if self.channels > 1:
            image = np.reshape(a=image, newshape=(
                self.height, self.width, self.channels))
            image = cv2.cvtColor(src=image, code=self.color_code)
            image = np.array(image)
        else:
            image = np.reshape(a=image, newshape=(self.height, self.width))
        return image

    def _start_image_queue(self):
        self.framrate_int = int(float(self.config['Timing']['Framerate']))

        for i in range(self.framrate_int):
            mem_ptr = ueye.c_mem_p()
            mem_id = ueye.int()
            result = ueye.is_AllocImageMem(hCam=self.camera, width=self.width, height=self.height, bitspixel=self.bitspixel, ppcImgMem=mem_ptr, pid=mem_id)
            self._check(result=result, info='alloc mem fail')
            result = ueye.is_SetImageMem(hCam=self.camera, pcMem=mem_ptr, id=mem_id)
            self._check(result=result, info='set mem error')
            result = ueye.is_AddToSequence(hCam=self.camera, pcMem=mem_ptr, nID=mem_id)
            self._check(result=result, info='add mem to sequence error')
            print('add ', mem_id.value, ' at ', mem_ptr)

        result = ueye.is_InitImageQueue(hCam=self.camera, nMode=ueye.int(0))
        self._check(result=result, info='Init Image Queue error')
        result = ueye.is_CaptureVideo(hCam=self.camera, Wait=ueye.IS_WAIT)
        self._check(result=result, info='Capture Video error')
        self.image_list = [0 for i in range(self.framrate_int)]
        self.image_list_pos = 0
        capture_loop = Thread(target=self._image_capture_loop, args=(), daemon=True)
        capture_loop.start()
        print('start queue capturing')

    def _image_capture_loop(self):
        ppcMem = ueye.c_mem_p()
        imageID = ueye.int()
        while 1:
            result = ueye.is_WaitForNextImage(hCam=self.camera, timeout=ctypes.c_uint(100), ppcMem=ppcMem, imageID=imageID)
            if result == 0:
                image = ueye.get_data(ppcMem.value, self.width, self.height, self.bitspixel, self.lineinc, copy=True)
                # print(image.shape)
                # print(image)
                if self.channels > 1:
                    image = np.reshape(a=image, newshape=(
                        self.height, self.width, self.channels))
                    image = cv2.cvtColor(src=image, code=self.color_code)
                    image = np.array(image)
                else:
                    image = np.reshape(a=image, newshape=(self.height, self.width))
                # print(image.shape)
                #print(type(image), self.image_list_pos)
                self.image_list[self.image_list_pos] = image
                self.image_list_pos = (self.image_list_pos+1) % self.framrate_int
                ueye.is_UnlockSeqBuf(hCam=self.camera, nNum=imageID, pcMem=ppcMem.value)
            elif result != ueye.IS_TIMED_OUT:
                print('something ain''t right,error code ', result)
            else:
                sleep(0.1)

    def release(self):
        result = ueye.is_ExitCamera(hCam=self.camera)
        self._check(result=result, info='exit camera')


class GUI:
    def __init__(self, project_parameters):
        # parameters
        self.project_parameters = project_parameters
        self.camera = IDSCAMERA(
            camera_parameter_path=project_parameters.camera_parameter_path)
        self.predict_object = Predict(project_parameters=project_parameters)
        self.folder_path = None
        self.backup_t = None
        self.pos_backup = 0
        # window
        self.window = Tk()
        self.window.geometry('{}x{}'.format(
            self.window.winfo_screenwidth(), self.window.winfo_screenheight()))
        self.window.title('IDS Camera GUI')

        # button
        self.load_folder_path_button = Button(
            self.window, text='選擇影像存放位置', fg='black', bg='white', command=self._load_folder_path)
        self.save_image_button = Button(
            self.window, text='儲存影像', fg='black', bg='white', command=self._save_image)

        # label
        self.filename_label = Label(self.window, text='檔案名稱', fg='black')
        self.filepath_label = Label(self.window, text='', fg='black')
        self.real_time_image_text_label = Label(
            self.window, text='', fg='black')
        self.real_time_image_label = Label(self.window, text='', fg='black')
        self.probability_label = Label(self.window, text='', fg='black')
        self.result_label = Label(
            self.window, text='', fg='black', font=(None, 50))

        # text
        self.filename_text = Text(self.window, height=2, width=10)

    def _load_folder_path(self):
        self.folder_path = filedialog.askdirectory(initialdir='./')

    def _save_image(self):
        if self.folder_path is None:
            messagebox.showerror(title='錯誤', message='尚未選取影像存放位置！')
        else:
            self.filename = join('{}_{}.png'.format(self.filename_text.get(
                '1.0', 'end-1c'), datetime.now().strftime('%Y%m%d%H%M%S%f')))
            self.image.save(join(self.folder_path, self.filename))
            self.filepath_label.config(text='檔案位置: {}'.format(
                join(self.folder_path, self.filename)))

    def _recognize_image(self, image):
        start = time()
        r, g, b = image.split()
        probability = self.predict_object(image=r)  # probability = self.predict_object(image=image)
        self.probability_label.config(text=('probability:\n'+' {}:{},'*len(probability)).format(
            *np.concatenate(list(zip(self.project_parameters.classes, probability))))[:-1])
        self.result_label.config(
            text=self.project_parameters.classes[probability.argmax()])
        end = time()
        print("i'm die. within ", (end-start))

    def _resize_image(self, image):
        width, height = image.size
        if self.window.winfo_height() == 1 or self.window.winfo_width() == 1:
            ratio = 1
        else:
            ratio = max(self.window.winfo_height(),
                        self.window.winfo_width())/max(width, height)
        ratio *= 0.5
        return image.resize((int(width*ratio), int(height*ratio)))

    def _get_image(self):
        start = time()
        mid_1 = time()
        # self.image = Image.fromarray(self.camera())
        while 1:
            pos = (self.camera.image_list_pos+self.camera.framrate_int-2) % self.camera.framrate_int
            if pos != self.pos_backup:
                break
        self.pos_backup = pos
        self.image = Image.fromarray(self.camera.image_list[pos])
        mid_2 = time()
        t = Thread(target=self._recognize_image, args=(self.image,), daemon=True)
        t.start()

        resized_image = self._resize_image(image=self.image)
        imageTk = ImageTk.PhotoImage(resized_image)

        self.real_time_image_text_label.config(text='即時影像:\n')
        self.real_time_image_label.config(image=imageTk)
        self.real_time_image_label.image = imageTk
        end = time()
        print(end-start, mid_2-mid_1, (mid_2-mid_1)/(end-start), 1/(end-start))
        self.real_time_image_label.after(ms=1, func=self._get_image)

    def __call__(self):
        # position, 1st column
        self.load_folder_path_button.pack(anchor=tk.NW)
        self.filename_label.pack(anchor=tk.NW)
        self.filename_text.pack(anchor=tk.NW)
        self.save_image_button.pack(anchor=tk.NW)

        # position, 2nd column
        self.real_time_image_text_label.pack(anchor=tk.N)
        self.real_time_image_label.pack(anchor=tk.N)
        self.filepath_label.pack(anchor=tk.N)
        self.probability_label.pack(anchor=tk.N)
        self.result_label.pack(anchor=tk.N)

        # run
        self._get_image()
        self.window.mainloop()
        self.camera.release()


if __name__ == '__main__':
    # project parameters
    project_parameters = ProjectParameters().parse()
    project_parameters.camera_parameter_path = 'parameters.ini'

    # create GUI object
    gui = GUI(project_parameters=project_parameters)

    # run
    gui()
