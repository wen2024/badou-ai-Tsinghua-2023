# -------------------------------------------------------------#
#   MobileNet的网络部分
# -------------------------------------------------------------#
import numpy as np
from keras import layers
from keras.models import Model
from keras.layers import Input, Dense, Reshape, Dropout, Conv2D, GlobalAveragePooling2D, DepthwiseConv2D, Activation, BatchNormalization
from keras.preprocessing.image import image_utils
from keras.applications.imagenet_utils import decode_predictions
from keras import backend as K


def relu6(x):
    return K.relu(x, max_value=6)


def _conv_block(inputs, filters, kernel_size=(3, 3), strides=(1, 1)):
    x = Conv2D(filters, kernel_size, padding='same', strides=strides, use_bias=False, name='conv1')(inputs)
    x = BatchNormalization(name='conv1_bn')(x)
    x = Activation(relu6, name='conv1_relu')(x)
    return x


def _depthwise_conv_block(inputs, pointwise_conv_filters, depth_multiplier=1, strides=(1, 1), block_id=1):
    x = DepthwiseConv2D(
        kernel_size=(3, 3),
        strides=strides,
        padding="same",
        depth_multiplier=depth_multiplier,
        activation=None,
        use_bias=False,
        name='conv_dw_%d' % block_id
    )(inputs)
    x = BatchNormalization(name='conv_dw_%d_bn' % block_id)(x)
    x = Activation(relu6, name='conv_dw_%d_relu' % block_id)(x)

    # 1x1 调整通道
    x = Conv2D(
        filters=pointwise_conv_filters,
        kernel_size=(1, 1),
        strides=(1, 1),
        padding="same",
        name='conv_pw_%d' % block_id
    )(x)
    x = BatchNormalization(name='conv_pw_%d_bn' % block_id)(x)
    return Activation(relu6, name='conv_pw_%d_relu' % block_id)(x)


def mobilenet(input_shape, classes=1000, depth_multiplier=1, dropout=1e-3):
    """
    :param input_shape:
    :param classes:
    :param depth_multiplier: 这里等于1，保证了输入通道等于输出的通道，通常用于depthwise conv，因为输出=输入通道*depth_multiplier
    :param dropout:
    :return:
    """

    img_input = Input(shape=input_shape)
    # 224,224,3 -> 112,112,32
    x = _conv_block(img_input, 32, strides=(2, 2))
    # 112,112,32 -> 112,112,64
    x = _depthwise_conv_block(x, 64, depth_multiplier, block_id=1)
    # 112,112,64 -> 56,56,128
    x = _depthwise_conv_block(x, 128, depth_multiplier, strides=(2, 2),  block_id=2)
    # 56,56,128 -> 56,56,128
    x = _depthwise_conv_block(x, 128, depth_multiplier, block_id=3)
    # 56,56,128 -> 28,28,256
    x = _depthwise_conv_block(x, 256, depth_multiplier, strides=(2, 2), block_id=4)
    # 28,28,256 -> 28,28,256
    x = _depthwise_conv_block(x, 256, depth_multiplier, block_id=5)
    # 28,28,256 -> 14,14,512
    x = _depthwise_conv_block(x, 512, depth_multiplier, strides=(2, 2), block_id=6)
    # 5个 14,14,512 -> 14,14,512
    x = _depthwise_conv_block(x, 512, depth_multiplier, block_id=7)
    x = _depthwise_conv_block(x, 512, depth_multiplier, block_id=8)
    x = _depthwise_conv_block(x, 512, depth_multiplier, block_id=9)
    x = _depthwise_conv_block(x, 512, depth_multiplier, block_id=10)
    x = _depthwise_conv_block(x, 512, depth_multiplier, block_id=11)
    # 14,14,512 -> 7,7,1024
    x = _depthwise_conv_block(x, 1024, depth_multiplier, strides=(2, 2), block_id=12)
    # 7,7,1024 -> 7,7,1024
    x = _depthwise_conv_block(x, 1024, depth_multiplier, block_id=13)
    # 7,7,1024 -> 1,1,1024
    x = GlobalAveragePooling2D(name='avg_pool')(x)
    x = Reshape((1, 1, 1024), name='reshape_1')(x)
    x = Dropout(dropout, name='dropout')(x)
    x = Conv2D(classes, kernel_size=(1, 1), padding='same', name='conv_preds')(x)
    x = Activation('softmax', name='act_softmax')(x)
    x = Reshape((classes, ), name='reshape_2')(x)
    inputs = img_input

    model = Model(inputs, x, name='mobilenet_1_0_224_tf')
    model.load_weights('mobilenet_1_0_224_tf.h5')
    return model


def preprocess_input(x):
    x /= 255
    x -= 0.5
    x *= 2.
    return x


if __name__ == '__main__':
    from mobilenet import MobileNet
    # model = mobilenet(input_shape=[224, 224, 3])

    model = MobileNet(input_shape=[224, 224, 3])
    img_path = '../../file/elephant.jpg'
    img = image_utils.load_img(img_path, target_size=(224, 224))
    x = image_utils.img_to_array(img)
    x = np.expand_dims(x, axis=0)
    x = preprocess_input(x)
    preds = model.predict(x)
    print(decode_predictions(preds, top=2))

    pass






