import tensorflow as tf
import numpy as np


class BBoxUtility(object):
    def __init__(self, priors=None, overlap_threshold=0.7, ignore_threshold=0.3,
                 nms_thresh=0.7, top_k=300):
        self.priors = priors
        self.num_priors = 0 if priors is None else len(priors)
        self.overlap_threshold = overlap_threshold
        self.ignore_threshold = ignore_threshold
        self._nms_thresh = nms_thresh
        self._top_k = top_k
        self.boxes = tf.placeholder(dtype='float32', shape=(None, 4))
        self.scores = tf.placeholder(dtype='float32', shape=(None,))
        self.nms = tf.image.non_max_suppression(self.boxes, self.scores,
                                                self._top_k,
                                                iou_threshold=self._nms_thresh)
        self.sess = tf.Session(config=tf.ConfigProto(device_count={'GPU': 0}))

    @property
    def nms_thresh(self):
        return self._nms_thresh

    @nms_thresh.setter
    def nms_thresh(self, value):
        self._nms_thresh = value
        self.nms = tf.image.non_max_suppression(self.boxes, self.scores,
                                                self._top_k,
                                                iou_threshold=self._nms_thresh)

    def iou(self, box):
        # 计算出每个真实框与所有的先验框的iou
        # 判断真实框与先验框的重合情况
        inter_upleft = np.maximum(self.priors[:, :2], box[:2])
        inter_botright = np.minimum(self.priors[:, 2:4], box[2:])  # 一个是最大，一个是最小
        inter_wh = inter_botright - inter_upleft
        inter_wh = np.maximum(inter_wh, 0)
        inter = inter_wh[:, 0] * inter_wh[:, 1]

        # 真实框的面积
        area_true = (box[2] - box[0]) * (box[3] - box[1])
        # 先验框面积
        area_gt = (self.priors[:, 2] - self.priors[:, 0]) * (self.priors[:, 3] - self.priors[:, 1])
        # 计算iou
        union = area_true + area_gt - inter
        iou = inter / union
        return iou

    def encode_box(self, box, return_iou=True):
        iou = self.iou(box)
        encoded_box = np.zeros((self.num_priors, 4 + return_iou))

        # 找到每一个与真实框重合程度较高的先验框
        assign_mask = iou > self.overlap_threshold
        # 如果都为False，则将最大的设置为True
        if not assign_mask.any():
            assign_mask[iou.argmax()] = True
        if return_iou:
            # 满足assign_mask的条件会赋值，其余为0
            encoded_box[:, -1][assign_mask] = iou[assign_mask]

        # 找到对应的先验框，这是所有的有效框
        assigned_priors = self.priors[assign_mask]
        # 逆向编码，将真实框转化为FasterRCNN预测结果的格式
        # 先计算真实框的中心与长宽
        box_center = 0.5 * (box[:2] + box[2:])
        box_wh = box[2:] - box[:2]
        # 再计算重合程度较高的先验框的中心与长宽
        assigned_priors_center = 0.5 * (assigned_priors[:, :2] + assigned_priors[:, 2:4])
        assigned_priors_wh = assigned_priors[:, 2:4] - assigned_priors[:, :2]
        # 边框回归，得到的位置信息是偏移量。4是自定义的参数，用于改变量程，更好的训练，后文对应
        encoded_box[:, :2][assign_mask] = box_center - assigned_priors_center
        encoded_box[:, :2][assign_mask] /= assigned_priors_wh
        encoded_box[:, :2][assign_mask] *= 4

        encoded_box[:, 2:4][assign_mask] = np.log(box_wh / assigned_priors_wh)
        encoded_box[:, 2:4][assign_mask] *= 4
        return encoded_box.ravel()

    def ignore_box(self, box):
        iou = self.iou(box)
        # 38x38x9, 1，用于储存所有先验框与真实框的iou值
        ignored_box = np.zeros((self.num_priors, 1))

        # 找到每一个真实框，重合程度较高的先验框
        assign_mask = (iou > self.ignore_threshold) & (iou < self.overlap_threshold)

        if not assign_mask.any():
            assign_mask[iou.argmax()] = True
        # 第一列，每个值，满足assign_mask赋值
        ignored_box[:, 0][assign_mask] = iou[assign_mask]
        return ignored_box.ravel()

    def assign_boxes(self, boxes, anchors):
        # 先验框个数 1444x9
        self.num_priors = len(anchors)
        self.priors = anchors
        # (x_min, y_min, x_max, y_max)+目标框所属类别 是否有效
        assignment = np.zeros((self.num_priors, 4 + 1))

        assignment[:, 4] = 0.0
        if len(boxes) == 0:
            return assignment

        # 对每一个真实框都进行iou计算，将boxes[:, :4]的每一行用于self.ignore_box函数，第二个轴->每一行
        # 每一个满足忽略条件的先验框与真实框的iou的值
        ignored_boxes = np.apply_along_axis(self.ignore_box, 1, boxes[:, :4])

        # 取重合程度最大的先验框，并且获取这个先验框的index
        # 将第二个维度复制到第三个维度，以适应后续计算，第三个维度也是每个iou
        ignored_boxes = ignored_boxes.reshape(-1, self.num_priors, 1)  # -1,1444x9,1
        # 取iou的最大值，与n个真实框的iou n,12996,1
        ignore_iou = ignored_boxes[:, :, 0].max(axis=0)
        ignore_iou_mask = ignore_iou > 0

        assignment[:, 4][ignore_iou_mask] = -1

        # 每个有效框的坐标和与真实框的iou
        encoded_boxes = np.apply_along_axis(self.encode_box, 1, boxes[:, :4])
        encoded_boxes = encoded_boxes.reshape(-1, self.num_priors, 5)

        # 取与其中一个真实框重合程度最高的先验框的iou
        best_iou = encoded_boxes[:, :, -1].max(axis=0)
        # 取出这些iou中最大的值的先验框的索引
        best_iou_idx = encoded_boxes[:, :, -1].argmax(axis=0)
        best_iou_mask = best_iou > 0
        # 得到最接近真实框的先验框的索引
        best_iou_idx = best_iou_idx[best_iou_mask]

        assign_num = len(best_iou_idx)
        # 保留重合程度最大的先验框的应该有的预测结果
        encoded_boxes = encoded_boxes[:, best_iou_mask, :]
        # 赋值
        assignment[:, :4][best_iou_mask] = encoded_boxes[best_iou_idx, np.arange(assign_num), :4]
        # 4表示为有效框
        assignment[:, 4][best_iou_mask] = 1

        # 通过assign_boxes我们就获得了，输入进来的这张图片，应该有的预测结果是什么样子的（-1背景，1有效）
        return assignment

    def decode_boxes(self, mbox_loc, mbox_priorbox):
        # 获取先验框的宽高[12996,4]
        prior_width = mbox_priorbox[:, 2] - mbox_priorbox[:, 0]
        prior_height = mbox_priorbox[:, 3] - mbox_priorbox[:, 1]
        # 获得先验框的中点
        prior_center_x = 0.5 * (mbox_priorbox[:, 2] + mbox_priorbox[:, 0])
        prior_center_y = 0.5 * (mbox_priorbox[:, 3] + mbox_priorbox[:, 1])
        # 真实框距离先验框中心的xy轴偏移情况（对应前文）
        decode_bbox_center_x = mbox_loc[:, 0] * prior_width / 4
        decode_bbox_center_x += prior_center_x
        decode_bbox_center_y = mbox_loc[:, 1] * prior_height / 4
        decode_bbox_center_y += prior_center_y
        # 真实框的宽高求取
        decode_bbox_width = np.exp(mbox_loc[:, 2] / 4)
        decode_bbox_width *= prior_width
        decode_bbox_height = np.exp(mbox_loc[:, 3] / 4)
        decode_bbox_height *= prior_height
        # 获取真实框的左上角和右下角
        decode_bbox_xmin = decode_bbox_center_x - 0.5 * decode_bbox_width
        decode_bbox_ymin = decode_bbox_center_y - 0.5 * decode_bbox_height
        decode_bbox_xmax = decode_bbox_center_x + 0.5 * decode_bbox_width
        decode_bbox_ymax = decode_bbox_center_y + 0.5 * decode_bbox_height
        # 真实框的左上角和右下角进行堆叠
        decode_bbox = np.concatenate((decode_bbox_xmin[:, None],
                                      decode_bbox_ymin[:, None],
                                      decode_bbox_xmax[:, None],
                                      decode_bbox_ymax[:, None]),
                                     axis=-1)
        # 防止超出0与1
        decode_bbox = np.minimum(np.maximum(decode_bbox, 0.0), 1.0)
        return decode_bbox

    def detection_out(self, predictions, mbox_priorbox, num_classes, keep_top_k=300,
                      confidence_threshold=0.5):
        # 网络预测结果
        # 置信度
        mbox_conf = predictions[0]  # 0-1
        mbox_loc = predictions[1]  # 偏移位置信息
        # 先验框
        mbox_priorbox = mbox_priorbox
        results = []
        # 对每一个图片进行处理
        for i in range(len(mbox_loc)):
            results.append([])
            decode_bbox = self.decode_boxes(mbox_loc[i], mbox_priorbox)
            for c in range(num_classes):
                c_confs = mbox_conf[i, :, c]
                c_confs_m = c_confs > confidence_threshold
                if len(c_confs[c_confs_m]) > 0:
                    # 取出得分最高的confidence_threshold的框
                    boxes_to_process = decode_bbox[c_confs_m]
                    confs_to_process = c_confs[c_confs_m]
                    # 进行iou的非极大抑制
                    feed_dict = {
                        self.boxes: boxes_to_process,
                        self.scores: confs_to_process
                    }
                    idx = self.sess.run(self.nms, feed_dict=feed_dict)
                    # 取出在非极大值抑制中效果较好的内容
                    good_boxes = boxes_to_process[idx]
                    confs = confs_to_process[idx][:, None]
                    # 将label、置信度、框的位置进行堆叠
                    labels = c * np.ones((len(idx), 1))
                    c_pred = np.concatenate((labels, confs, good_boxes), axis=1)
                    # 添加进results里
                    results[-1].extend(c_pred)

            if len(results[-1]) > 0:
                # 按置信度顺序排列
                results[-1] = np.array(results[-1])
                # 由高到低
                argsort = np.argsort(results[-1][:, 1])[::-1]
                results[-1] = results[-1][argsort]
                # 选出置信度最大的keep_top_k个
                results[-1] = results[-1][:keep_top_k]
        # 获得，在所有预测结果里面，置信度比较高的框
        # 还有，利用先验框和Retinanet的预测结果，处理获得了真实框（预测框）的位置
        return results

    def nms_for_out(self, all_labels, all_confs, all_bboxes, num_classes, nms):
        results = []
        nms_out = tf.image.non_max_suppression(self.boxes, self.scores,
                                               self._top_k,
                                               iou_threshold=nms)
        for c in range(num_classes):
            c_pred = []
            mask = all_labels == c
            if len(all_confs[mask]) > 0:
                # 取出得分高于confidence_threshold的框
                boxes_to_process = all_bboxes[mask]
                confs_to_process = all_confs[mask]
                # 进行iou的非极大抑制
                feed_dict = {self.boxes: boxes_to_process,
                             self.scores: confs_to_process}
                idx = self.sess.run(nms_out, feed_dict=feed_dict)
                # 取出在非极大抑制中效果较好的内容
                good_boxes = boxes_to_process[idx]
                confs = confs_to_process[idx][:, None]
                # 将label、置信度、框的位置进行堆叠。
                labels = c * np.ones((len(idx), 1))
                c_pred = np.concatenate((labels, confs, good_boxes), axis=1)
            results.extend(c_pred)
        return results