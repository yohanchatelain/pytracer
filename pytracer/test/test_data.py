import sys
import os

root_path = "pytracer/test"

internal_tests = {
    "path": "internal",
    "names": set(["hook", "basic"])
}

sklearn_tests = {
    "path": "sklearn",
    "names": set(["basic_tests",
                  "bayesian_ridge_regression",
                  "cluster_iris",
                  "digits_classifications",
                  "l1_penalty_and_sparsity_in_logistic_regression",
                  "lasso_and_elastic_net_for_sparse_signals",
                  "mnist_classification_using_multinomial_logistic_l1",
                  "multitask_lasso",
                  "orthogonal_matching_pursuit",
                  "pca_iris",
                  "poisson_regression_non_normal_loss",
                  "segmentation_toy",
                  "sgd",
                  "tweedie_regression_insurance_claims"
                  ])
}


def get_set(obj):
    _new_set = None
    if isinstance(obj, str):
        _new_set = set([obj])
    elif isinstance(obj, list):
        _new_set = set(obj)
    elif isinstance(obj, set):
        _new_set = obj
    return _new_set


def get_test_filename(name):
    return f"test_{name}.py"


def get_test_path(tests, include=None, exclude=None):
    path = tests["path"]
    tests = tests["names"]
    if include and exclude:
        sys.exit("Error get_test_path function, can use include/exclude together")
    if include:
        include = get_set(include)
        included_test = tests & include
    elif exclude:
        exclude = get_set(exclude)
        included_test = tests - exclude
    else:
        included_test = tests
    return [os.path.join(root_path, path, get_test_filename(name)) for name in included_test]
