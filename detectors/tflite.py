from tensorflow.lite.python.interpreter import Interpreter
import numpy as np
import cv2
import odrpc
from detectors.labels import load_labels

input_mean = 127.5
input_std = 127.5

class TensorflowLite:
    def __init__(self, config):
        self.config = odrpc.Detector(**{
            'name': config['name'],
            'type': 'tensorflow2',
            'labels': [],
            'model': config['modelFile']
        })

        # Load the Tensorflow Lite model.
        # If using Edge TPU, use special load_delegate argument
        if 'hwAccel' in config and config['hwAccel']:
            from tensorflow.lite.python.interpreter import load_delegate
            self.interpreter = Interpreter(model_path=config['modelFile'],
                                    experimental_delegates=[load_delegate('libedgetpu.so.1.0')])
        else:
            self.interpreter = Interpreter(model_path=config['modelFile'])
        
        self.interpreter.allocate_tensors()

        # Get model details
        self.input_details = self.interpreter.get_input_details()
        self.output_details = self.interpreter.get_output_details()
        self.height = self.input_details[0]['shape'][1]
        self.width = self.input_details[0]['shape'][2]
        self.floating_model = (self.input_details[0]['dtype'] == np.float32)

        # Load labels
        self.labels = load_labels(config['labelFile'])
        for i in self.labels:
            self.config.labels.append(self.labels[i])

    def detect(self, image):

        image_resized = cv2.resize(image, (self.width, self.height))
        input_data = np.expand_dims(image_resized, axis=0)

        # Normalize pixel values if using a floating model (i.e. if model is non-quantized)
        if self.floating_model:
            self.input_data = (np.float32(self.input_data) - input_mean) / input_std

        # Perform the actual detection by running the model with the image as input
        self.interpreter.set_tensor(self.input_details[0]['index'],input_data)
        self.interpreter.invoke()

        boxes = self.interpreter.get_tensor(self.output_details[0]['index'])[0] # Bounding box coordinates of detected objects
        classes = self.interpreter.get_tensor(self.output_details[1]['index'])[0] # Class index of detected objects
        scores = self.interpreter.get_tensor(self.output_details[2]['index'])[0] # Confidence of detected objects

        ret = odrpc.DetectResponse()
        for i in range(len(scores)):
            detection = odrpc.Detection()
            (detection.top, detection.left, detection.bottom, detection.right) = boxes[i].tolist()
            detection.confidence = scores[i] * 100.0
            label = self.labels[int(classes[i])]
            if label:
                detection.label = label
            ret.detections.append(detection)
        return ret

