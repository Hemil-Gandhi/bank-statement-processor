"""Classical ML feature pipelines (TF-IDF char + word n-grams)."""
from __future__ import annotations

from sklearn.calibration import CalibratedClassifierCV
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.svm import LinearSVC


def make_features() -> FeatureUnion:
    char = TfidfVectorizer(
        analyzer="char_wb",
        ngram_range=(2, 5),
        min_df=1,
        sublinear_tf=True,
        max_features=80_000,
    )
    word = TfidfVectorizer(
        analyzer="word",
        ngram_range=(1, 2),
        min_df=1,
        sublinear_tf=True,
        max_features=40_000,
        token_pattern=r"(?u)\b[\w@]+\b",
    )
    return FeatureUnion([("char", char), ("word", word)])


def make_pipeline(estimator: str = "logreg") -> Pipeline:
    if estimator == "svm":
        model = CalibratedClassifierCV(
            estimator=LinearSVC(C=1.0, class_weight="balanced", max_iter=5000),
            cv=3,
            method="sigmoid",
        )
    elif estimator == "nb":
        model = MultinomialNB(alpha=0.2)
    else:
        model = LogisticRegression(
            max_iter=3000,
            C=5.0,
            class_weight="balanced",
            solver="lbfgs",
        )
    return Pipeline([("features", make_features()), ("model", model)])
