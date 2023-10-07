import tensorflow as tf
import numpy as np
from PIL import Image
from collections import defaultdict


def load_weights(var_list, weights_file):
    """
    加载预训练好的darknet53权重文件
    :param var_list: 赋值变量名
    :param weights_file: 权重文件
    :return:
    assign_ops: 赋值更新操作
    """
    with open(weights_file, "rb") as fp:
        _ = np.fromfile(fp, dtype=np.int32, count=5)
        weights = np.fromfile(fp, dtype=np.float32)

    ptr = 0
    i = 0
    assign_ops = []
    while i < len(var_list) - 1:
        var1 = var_list[i]
        var2 = var_list[i + 1]
        # 当处理conv层时
        if 'conv2d' in var1.name.split('/')[-2]:
            # 检查下一层的类型
            if 'batch_normalization' in var2.name.split('/')[-2]:
                # 加载batch norm参数
                gamma, beta, mean, var = var_list[i + 1:i + 5]
                batch_norm_vars = [beta, gamma, mean, var]
                for var in batch_norm_vars:
                    shape = var.shape.as_list()
                    num_params = np.prod(shape)
                    var_weights = weights[ptr:ptr + num_params].reshape(shape)
                    ptr += num_params
                    assign_ops.append(tf.assign(var, var_weights, validate_shape=True))
                # 将指针移动4，因为加载了四个变量
                i += 4
            elif 'conv2d' in var2.name.split('/')[-2]:
                # 加载biases
                bias = var2
                bias_shape = bias.shape.as_list()
                bias_params = np.prod(bias_shape)
                bias_weights = weights[ptr:ptr + bias_params].reshape(bias_shape)
                ptr += bias_params
                assign_ops.append(tf.assign(bias, bias_weights, validate_shape=True))
                # 加载了一个变量
                i += 1

            # 我们可以加载conv层的权重
            shape = var1.shape.as_list()
            num_params = np.prod(shape)

            var_weights = weights[ptr:ptr + num_params].reshape((shape[3], shape[2], shape[0], shape[1]))
            # 转置
            var_weights = np.transpose(var_weights, (2, 3, 1, 0))
            ptr += num_params
            assign_ops.append(tf.assign(var1, var_weights, validate_shape=True))
            i += 1
    return assign_ops


def letterbox_image(image, size):
    """
    对预测输入图象进行缩放，按照长款比进行缩放，不足的地方进行填充
    :param image:输入图象
    :param size:缩放后的大小
    :return boxed_image:缩放后的图象
    """
    image_w, image_h = image.size
    w, h = size
    new_w = int(image_w * min(w * 1.0 / image_w, h * 1.0 / image_h))
    new_h = int(image_h * min(w * 1.0 / image_w, h * 1.0 / image_h))
    resized_image = image.resize((new_w, new_h), Image.BICUBIC)

    boxed_image = Image.new('RGB', size, (128, 128, 128))
    boxed_image.paste(resized_image, ((w - new_w) // 2, (h - new_h) // 2))
    return boxed_image

