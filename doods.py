import os
import yaml
import base64
import numpy as np
import cv2

import odrpc

from detectors.tesnorflow import Tensorflow
from detectors.tensorflow2 import Tensorflow2
from detectors.tflite import TensorflowLite

# dict from detector type to class
detectors = {
    "tensorflow": Tensorflow,
    "tensorflow2": Tensorflow2,
    "tflite": TensorflowLite,
}

font                   = cv2.FONT_HERSHEY_PLAIN
fontScale              = 1.3
thickness              = 1
lineType               = 4

class MissingDetector:
    def __init__(self, dconfig):
        raise Exception(f'''Unknown detector type {dconfig['type']}.''')

class Doods:
    def __init__(self):
        # Load config file
        config_file = os.environ.get('CONFIG_FILE', 'config.yaml')
        with open(config_file, 'r') as stream:
            try:
                self.config = yaml.safe_load(stream)
            except yaml.YAMLError as exc:
                print(exc)

        # Initialize the detectors
        self._detectors = {}
        for dconfig in self.config['doods']['detectors']:
            detector_class = detectors.get(dconfig['type'], MissingDetector)
            detector = detector_class(dconfig)
            self._detectors[dconfig['name']] = detector

    # Get the detectors configs
    def detectors(self):
        detectors = []
        for name in self._detectors:
            detectors.append(self._detectors[name].config)
        return detectors

    # Detect image
    def detect(self, detect, return_image=False):
        # Get the detector
        if not detect.detector_name:
            detect.detector_name = 'default'
        detector = self._detectors[detect.detector_name]
        if not detector:
            ret = odrpc.DetectResponse
            ret.error = "could not determine detector"
            return ret

        # Decode the image
        image_data = base64.b64decode(detect.data)
        image_bytes = np.frombuffer(image_data, dtype=np.uint8)
        image = cv2.imdecode(image_bytes, cv2.IMREAD_COLOR)

        # Handle preprocessing
        for process in detect.preprocess:
            if process == 'grayscale':
                image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
                # image = image[np.newaxis,:, :, np.newaxis]
            else:
                raise 'Whatever'

        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

        # Run detection
        ret = detector.detect(image)
        if not ret.error:
            ret.detections = Doods.filter_detections(ret.detections, detect.detect, detect.regions)
        ret.id = detect.id

        if not return_image:
            return ret

        # Convert the image back to BGR for saving
        image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
        height, width, channels = image.shape

        # Draw the global labels
        global_labels = []
        for label in detect.detect:
            global_labels.append("%s:%s" % (label, detect.detect[label]))
        if len(global_labels) > 0:
            cv2.putText(image, ','.join(global_labels), (5, 15), font, fontScale, (255, 255, 0), thickness, lineType)

        for region in detect.regions:
            region_labels = []
            for label in region.detect:
                region_labels.append("%s:%s" % (label, region.detect[label]))
            cv2.putText(image, ','.join(region_labels), (int(region.left*width), int(region.top*height)-2), font, fontScale, (255, 0, 255), thickness, lineType)
            cv2.rectangle(image, (int(region.left*width), int(region.top*height)), (int(region.right*width), int(region.bottom*height)), color=(255, 0, 255), thickness=2)

        # Draw the detections
        for detection in ret.detections:
            cv2.putText(image, "%s:%s" % (detection.label, detection.confidence), (int(detection.left*width), int(detection.top*height)-2), font, fontScale, (0, 255, 0), thickness, lineType)
            cv2.rectangle(image, (int(detection.left*width), int(detection.top*height)), (int(detection.right*width), int(detection.bottom*height)), color=(0, 255, 0), thickness=2)

        return cv2.imencode('.jpg', image)[1].tostring()

    @staticmethod
    def filter_detections(detections, detect, regions):
        ret = {}
        for i, d in enumerate(detections):
            if '*' in detect and d.confidence >= detect['*']:
                ret[i] = d
                continue
            if d.label in detect and d.confidence >= detect[d.label]:
                ret[i] = d
                continue
            for r in regions:
                if (
                    ( r.covers and r.top <= d.top and r.left <= d.left and r.bottom >= d.bottom and r.right >= d.right ) or
                    ( not r.covers and d.top <= r.bottom and d.left <= r.right and d.bottom >= r.top and d.right >= r.left )
                ):
                    if '*' in r.detect and d.confidence >= r.detect['*']:
                        ret[i] = d
                        break
                    if d.label in r.detect and d.confidence >= r.detect[d.label]:
                        ret[i] = d
                        break
        return list(ret.values())
