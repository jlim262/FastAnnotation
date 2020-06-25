
import cv2
import numpy as np
import kivy
from kivy.app import App
from kivy.uix.image import Image
from kivy.lang import Builder
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.effectwidget import EffectWidget, InvertEffect
from glob import glob
from kivy.uix.widget import Widget
from kivy.graphics.texture import Texture
from client.screens.common import TransparentBlackEffect
from time import sleep
from kivy.graphics import Rectangle, Fbo, Color
from kivy.clock import Clock
import random
import time

import numpy as np
import cython
from numba.typed import List


def mat2texture(mat):
    if mat.shape[-1] is not 4:
        mat = cv2.flip(mat, 0)
        mat = cv2.cvtColor(mat, cv2.COLOR_BGR2RGBA)
    buf = mat.tostring()
    tex = Texture.create(size=(mat.shape[1], mat.shape[0]), colorfmt='rgba')
    tex.blit_buffer(buf, colorfmt='rgba', bufferfmt='ubyte')
    return tex


class MyApp(App):
    i = 0
    stack_capacity = 100

    def __init__(self, shape, **kwargs):
        super().__init__(**kwargs)
        self.shape = shape
        self.image = np.zeros(shape=shape, dtype=np.uint8)
        self.image[:] = (0, 0, 255)
        self.stackmat = np.empty(shape=(np.product(shape), self.stack_capacity), dtype=np.uint8)
        self.stackmat_col = 0
        self.add_layer(self.image)

    def build(self):
        box = BoxLayout()
        self.img = Image(texture=mat2texture(self.image))

        box.add_widget(self.img)
        Clock.schedule_interval(lambda dt: self.add_random(), 0.01)

        return box

    def add_random(self):


        t0 = time.time()

        mat = np.zeros(shape=self.shape, dtype=np.uint8)
        center = (random.randint(0, 2000), random.randint(0, 1500))
        radius = random.randint(5, 50)
        color = tuple(np.random.choice(range(1,256), size=4).tolist())
        cv2.circle(mat, center=center, radius=radius, color=color, thickness=-1)

        self.add_layer(mat)

        self.display()

        self.i += 1
        t1 = time.time()
        print("TEST %d - %f" % (self.i, t1 - t0))



    def add_layer(self, mat):
        # self.stackmat = np.append(self.stackmat, mat.ravel(order='C')[:, np.newaxis], 1)
        if self.stackmat_col == self.stack_capacity:
            new_capacity = self.stack_capacity * 4
            stack = np.empty(shape=(np.product(self.shape), new_capacity), dtype=np.uint8)
            stack[:, :self.stack_capacity] = self.stackmat
            self.stackmat = stack
            self.stack_capacity = new_capacity

        self.stackmat[:, self.stackmat_col] = mat.flatten()
        self.stackmat_col += 1




    # Reaches 1s delay at 58 (27 on laptop)
    def calculate_buffer(self):
        buf = np.zeros(np.product(self.shape), dtype=np.uint8)
        for layer in reversed(self.stack):
            buf[buf == 0] = layer[buf == 0]

        buf[buf == 0] = self.image.flatten(order='C')[buf == 0]
        return buf

    # Reaches 1s delay at 125 (67 on laptop)
    def calculate_buffer2(self):
        buf = np.vstack(tuple(reversed(self.stack)) + (self.image.ravel(order='C'),))
        buf = np.transpose(buf)
        return buffer_calc(buf)

    #Reaches 1s delay at 330 (80 on my laptop)
    def calculate_buffer3(self):
        buf = np.vstack(tuple(reversed(self.stack)) + (self.image.ravel(order='C'),))
        buf = np.transpose(buf)
        return buffer_calc_p(buf)

    # 19 on laptop
    def calc_buffer4(self):
        layers = (self.image.ravel(order='C'),) + tuple(self.stack)
        return buffer_calc_list(layers)

    def calc_buffer5(self):
        layers = (self.image.ravel(order='C'),) + tuple(self.stack)
        return buffer_calc_p_list(layers)


    # Ran out of RAM at 160 layers (0.62s max)
    def calc_buffer6(self):
        # c2 = np.concatenate(self.stack, axis=0)
        c2 = self.stackmat[:, :self.stackmat_col]
        return buffer_calc_p2(c2)

    hist = None
    # 0.6s ,max at 200
    def calc_buffer7(self):
        if self.hist is None:
            self.hist = np.zeros(self.stackmat.shape[0], dtype=np.int)
        c2 = self.stackmat[:, :self.stackmat_col]
        buf = buffer_calc_2stage(c2, self.hist)
        return buf

    def display(self):
        buf = self.calc_buffer6()

        self.img.texture.blit_buffer(buf, colorfmt='rgb', bufferfmt='ubyte')
        self.img.canvas.ask_update()


import numba
from numba import jit


@jit(nopython=True)
def buffer_calc(stack):
    out = np.zeros(stack.shape[0], dtype=np.uint8)
    for i in range(stack.shape[0]):
        for j in range(stack.shape[1]):
            if stack[i, j] == 0:
                continue
            out[i] = stack[i, j]
            break
    return out

@jit(nopython=True, parallel=True)
def buffer_calc_p(stack):
    out = np.zeros(stack.shape[0], dtype=np.uint8)
    for i in numba.prange(stack.shape[0]):
        for j in range(stack.shape[1]):
            if stack[i, j] == 0:
                continue
            out[i] = stack[i, j]
            break
    return out

@jit(nopython=True, parallel=True)
def buffer_calc_p2(stack):
    width = stack.shape[1]
    height = stack.shape[0]
    out = np.zeros(height, dtype=np.uint8)
    for i in numba.prange(height):
        for j in range(width):
            reverse_j = width - 1 - j
            if stack[i, reverse_j] > 0:
                out[i] = stack[i, reverse_j]
                break
    return out

@jit(nopython=True, parallel=True)
def buffer_calc_2stage(stack, hist):
    width = stack.shape[1]
    height = stack.shape[0]
    out = np.zeros(height, dtype=np.uint8)
    for i in numba.prange(height):
        j1 = width - 1
        j2 = hist[i]
        if stack[i, j1] > 0:
            hist[i] = j1
            out[i] = stack[i, j1]
        elif stack[i, j2] > 0:
            hist[i] = j2
            out[i] = stack[i, j2]
        else:
            for j in range(width - 1):
                reverse_j = width - 1 - j
                if stack[i, reverse_j] > 0:
                    hist[i] = reverse_j
                    out[i] = stack[i, reverse_j]
                    break
    return out


@jit(nopython=True, parallel=True)
def buffer_calc_arrays(stack):
    width = stack.shape[1]
    height = stack.shape[0]
    out = np.zeros(height, dtype=np.uint8)
    for i in numba.prange(height):
        for j in range(width):
            reverse_j = width - 1 - j
            if stack[i, reverse_j] > 0:
                out[i] = stack[i, reverse_j]
                break
    return out


@jit(nopython=True, parallel=True)
def buffer_calc_p3(*stacks):
    n_stacks = len(stacks)
    width = stacks[0].shape[1]
    height = stacks[0].shape[0]
    out = np.zeros(height, dtype=np.uint8)
    for k in numba.prange(n_stacks):
        for i in numba.prange(height):
            for j in range(width):
                reverse_j = width - 1 - j
                if stacks[k][i, reverse_j] > 0:
                    out[i] = stacks[k][i, reverse_j]
                    break
    return out

@jit(nopython=True, parallel=True)
def buffer_calc_list(layers):
    width = len(layers[0])
    height = len(layers)
    out = [0] * height
    for j in numba.prange(height):
        for i in range(width):
            reverse_i = width - 1 - i
            if layers[j][reverse_i] > 0:
                out[j] = layers[j][reverse_i]
                break
    return out

@jit(nopython=True, parallel=True)
def buffer_calc_p_list(layers):
    width = len(layers)
    height = layers[0].shape[0]
    out = np.zeros(height, dtype=np.uint8)

    for j in numba.prange(height):
        for i in range(width):
            reverse_i = width - 1 - i
            if layers[reverse_i][j] > 0:
                out[j] = layers[reverse_i][j]
    return out

MyApp((2000,1500,3)).run()