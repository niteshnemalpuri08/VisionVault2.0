from flask import Blueprint, request, jsonify
import numpy as np

bp = Blueprint('ml', __name__)


def sigmoid(x):
    return 1 / (1 + np.exp(-np.clip(x, -500, 500)))


@bp.route('/predict', methods=['POST'])
def predict():
    try:
        data = request.get_json() or {}

        math = float(data.get('math', 0))
        phy  = float(data.get('physics', 0))
        chem = float(data.get('chemistry', 0))
        cs   = float(data.get('cs', 0))
        eng  = float(data.get('english', 0))
        att  = float(data.get('attendance', 0))

        features = np.array([math, phy, chem, cs, eng, att]) / 100.0
        weights  = np.array([0.16, 0.16, 0.16, 0.12, 0.12, 0.28])
        bias     = -0.45

        score = float(np.dot(features, weights)) + bias
        if att > 90:
            score += 0.2

        probability = float(sigmoid(score))
        return jsonify({
            'prediction': 1 if probability >= 0.5 else 0,
            'probability': round(probability, 4)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500