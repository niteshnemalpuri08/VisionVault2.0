import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

model = None


def train_model():
    global model
    print("🧠 Training ML predictor…")
    np.random.seed(42)
    n = 500
    df = pd.DataFrame({
        'math': np.random.randint(40, 100, n),
        'phy':  np.random.randint(40, 100, n),
        'chem': np.random.randint(40, 100, n),
        'cs':   np.random.randint(40, 100, n),
        'eng':  np.random.randint(40, 100, n),
        'pe':   np.random.randint(40, 100, n),
        'attendance': np.random.randint(50, 100, n),
    })
    avg = (df['math'] + df['phy'] + df['chem'] + df['cs'] + df['eng'] + df['pe']) / 6
    df['final_score'] = (avg * 0.7) + (df['attendance'] * 0.3) + np.random.normal(0, 2, n)

    X = df[['math', 'phy', 'chem', 'cs', 'eng', 'pe', 'attendance']]
    y = df['final_score']
    model = LinearRegression()
    model.fit(X, y)
    print("✅ ML predictor trained.")


def predict_score(math, phy, chem, cs, eng, pe, attendance):
    if model is None:
        train_model()
    X = pd.DataFrame([[math, phy, chem, cs, eng, pe, attendance]],
                     columns=['math', 'phy', 'chem', 'cs', 'eng', 'pe', 'attendance'])
    return round(float(np.clip(model.predict(X)[0], 0, 100)), 2)


# Auto-train on import
if __name__ != '__main__':
    train_model()