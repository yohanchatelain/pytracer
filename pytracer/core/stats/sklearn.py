import sklearn
import sklearn.cluster
import sklearn.svm
import sklearn.tree
import sklearn.decomposition
import sklearn.ensemble
import numpy as np

from pytracer.core.stats.numpy import StatisticNumpy

supported_instance = (sklearn.cluster.KMeans,
                      sklearn.svm.SVC,
                      sklearn.tree.DecisionTreeRegressor,
                      sklearn.tree._tree.Tree,
                      sklearn.decomposition.PCA,
                      sklearn.linear_model.SGDClassifier,
                      sklearn.linear_model.Lasso,
                      sklearn.linear_model.MultiTaskLasso,
                      sklearn.ensemble.AdaBoostRegressor,
                      sklearn.linear_model.RANSACRegressor,
                      sklearn.linear_model.LinearRegression)


def is_sklearn_value(value):
    return isinstance(value, supported_instance)


def get_sklearn_stat(data, type_):
    if type_ == sklearn.cluster.KMeans:
        return StatisticsSklearnKMeans(data).to_dict()
    elif type_ == sklearn.svm.SVC:
        return StatisticsSklearnSVC(data).to_dict()
    elif type_ == sklearn.tree.DecisionTreeRegressor:
        return StatisticsSklearnDecisionTreeRegressor(data).to_dict()
    elif type_ == sklearn.tree._tree.Tree:
        return StatisticsSklearnTree(data).to_dict()
    elif type_ == sklearn.decomposition.PCA:
        return StatisticsSklearnPCA(data).to_dict()
    elif type_ == sklearn.linear_model.SGDClassifier:
        return StatisticsSklearnSGDClassifier(data).to_dict()
    elif type_ == sklearn.linear_model.Lasso:
        return StatisticsSklearnLasso(data).to_dict()
    elif type_ == sklearn.linear_model.MultiTaskLasso:
        return StatisticsSklearnMultiTaskLasso(data).to_dict()
    elif type_ == sklearn.ensemble.AdaBoostRegressor:
        return StatisticsSklearnAdaBoostRegressor(data).to_dict()
    elif type_ == sklearn.linear_model.RANSACRegressor:
        return StatisticsSklearnRANSACRegressor(data).to_dict()
    elif type_ == sklearn.linear_model.LinearRegression:
        return StatisticsSklearnLinearRegression(data).to_dict()
    else:
        raise TypeError(f"{type_}")


class StatisticSklearn:

    def __init__(self, data):
        self._data = self.parse_data(data)

    def to_list(self):
        return list(self._data.values())

    def to_dict(self):
        return self._data


class StatisticsSklearnKMeans(StatisticSklearn):

    __attributes = ("cluster_centers_", "labels_", "inertia_", "n_iter_")

    def __init__(self, data):
        self.__attributes = StatisticsSklearnKMeans.__attributes
        self._data = self.parse_data(data)

    def parse_data(self, data):
        _data = dict()
        for attr in self.__attributes:
            for value in data:
                if hasattr(value, attr):
                    if attr in _data:
                        _data[attr].append(getattr(value, attr))
                    else:
                        _data[attr] = [getattr(value, attr)]

                    if (d := _data[attr]) == []:
                        _data[attr] = StatisticNumpy(np.array(d), empty=True)
                    else:
                        _data[attr] = StatisticNumpy(np.array(d))

        return _data


class StatisticsSklearnSVC(StatisticSklearn):

    __attributes = ("support_vectors_", "dual_coef_", "coef_", "intercept_",
                    "classes_", "probA_", "probB_", "class_weight_", "shape_fit_")

    def __init__(self, data):
        self.__attributes = StatisticsSklearnSVC.__attributes
        self._data = self.parse_data(data)

    def parse_data(self, data):
        _data = dict()
        for attr in self.__attributes:
            for value in data:
                if hasattr(value, attr):
                    obj = getattr(value, attr, None)
                    if obj is None:
                        _data[attr] = []
                        continue

                    if attr in _data:
                        _data[attr].append(obj)
                    else:
                        _data[attr] = [obj]

                    if (d := _data[attr]) == []:
                        empty = True
                    else:
                        empty = False
                    _data[attr] = StatisticNumpy(np.array(d), empty=empty)

        return _data


class StatisticsSklearnDecisionTreeRegressor(StatisticSklearn):

    __attributes = ("feature_importances_",)

    def __init__(self, data):
        self.__attributes = StatisticsSklearnDecisionTreeRegressor.__attributes
        self._data = self.parse_data(data)

    def parse_data(self, data):
        _data = dict()
        for attr in self.__attributes:
            for value in data:
                if hasattr(value, attr):
                    obj = getattr(value, attr, None)
                    if obj is None:
                        _data[attr] = []
                        continue

                    if attr in _data:
                        _data[attr].append(obj)
                    else:
                        _data[attr] = [obj]

                    if (d := _data[attr]) == []:
                        empty = True
                    else:
                        empty = False
                    _data[attr] = StatisticNumpy(np.array(d), empty=empty)

        tree_list = list()
        for value in data:
            tree = getattr(value, "tree_", None)
            if tree is None:
                break
            tree_list.append(tree)
            _data.update(StatisticsSklearnTree(tree_list).to_dict())

        return _data


class StatisticsSklearnTree(StatisticSklearn):

    __attributes = ("value", "threshold", "feature")

    def __init__(self, data):
        self.__attributes = StatisticsSklearnTree.__attributes
        self._data = self.parse_data(data)

    def parse_data(self, data):
        _data = dict()
        for attr in self.__attributes:
            for value in data:
                if hasattr(value, attr):
                    attr_name = f"Tree.{attr}"
                    if attr_name in _data:
                        _data[attr_name].append(getattr(value, attr))
                    else:
                        _data[attr_name] = [getattr(value, attr)]

                    if (d := _data[attr_name]) == []:
                        _data[attr_name] = StatisticNumpy(
                            np.array(d), empty=True)
                    else:
                        _data[attr_name] = StatisticNumpy(np.array(d))

        return _data


class StatisticsSklearnPCA(StatisticSklearn):

    __attributes = ("components_", "explained_variance_",
                    "explained_variance_ratio_", "singular_values_",
                    "mean_", "noise_variance_")

    def __init__(self, data):
        self.__attributes = StatisticsSklearnPCA.__attributes
        self._data = self.parse_data(data)

    def parse_data(self, data):
        _data = dict()
        for attr in self.__attributes:
            for value in data:
                if hasattr(value, attr):
                    attr_name = f"PCA.{attr}"
                    if attr_name in _data:
                        _data[attr_name].append(getattr(value, attr))
                    else:
                        _data[attr_name] = [getattr(value, attr)]

                    if (d := _data[attr_name]) == []:
                        _data[attr_name] = StatisticNumpy(
                            np.array(d), empty=True)
                    else:
                        _data[attr_name] = StatisticNumpy(np.array(d))

        return _data


class StatisticsSklearnSGDClassifier(StatisticSklearn):

    __attributes = ("coef_", "classes_", "intercept_")

    def __init__(self, data):
        self.__attributes = StatisticsSklearnSGDClassifier.__attributes
        self._data = self.parse_data(data)

    def parse_data(self, data):
        _data = dict()
        for attr in self.__attributes:
            for value in data:
                if hasattr(value, attr):
                    attr_name = f"SGDClassifier.{attr}"
                    if attr_name in _data:
                        _data[attr_name].append(getattr(value, attr))
                    else:
                        _data[attr_name] = [getattr(value, attr)]

                    if (d := _data[attr_name]) == []:
                        _data[attr_name] = StatisticNumpy(
                            np.array(d), empty=True)
                    else:
                        _data[attr_name] = StatisticNumpy(np.array(d))

        return _data


class StatisticsSklearnLasso(StatisticSklearn):

    __attributes = ("coef_", "sparse_coef_", "intercept_")

    def __init__(self, data):
        self.__attributes = StatisticsSklearnLasso.__attributes
        self._data = self.parse_data(data)

    def parse_data(self, data):
        _data = dict()
        for attr in self.__attributes:
            attr_name = f"Lasso.{attr}"
            for value in data:
                if hasattr(value, attr):
                    if attr_name in _data:
                        _data[attr_name].append(getattr(value, attr))
                    else:
                        _data[attr_name] = [getattr(value, attr)]

                    if (d := _data[attr_name]) == []:
                        _data[attr_name] = StatisticNumpy(
                            np.array(d), empty=True)
                    else:
                        _data[attr_name] = StatisticNumpy(np.array(d))

        return _data


class StatisticsSklearnMultiTaskLasso(StatisticSklearn):

    __attributes = ("coef_", "intercept_")

    def __init__(self, data):
        self.__attributes = StatisticsSklearnMultiTaskLasso.__attributes
        self._data = self.parse_data(data)

    def parse_data(self, data):
        _data = dict()
        for attr in self.__attributes:
            for value in data:
                if hasattr(value, attr):
                    attr_name = f"MultiTaskLasso.{attr}"
                    if attr_name in _data:
                        _data[attr_name].append(getattr(value, attr))
                    else:
                        _data[attr_name] = [getattr(value, attr)]

                    if (d := _data[attr_name]) == []:
                        _data[attr_name] = StatisticNumpy(
                            np.array(d), empty=True)
                    else:
                        _data[attr_name] = StatisticNumpy(np.array(d))

        return _data


class StatisticsSklearnAdaBoostRegressor(StatisticSklearn):

    __attributes = ("estimator_weights_", 'estimator_errors_',
                    'feature_importances_')

    def __init__(self, data):
        self.__attributes = StatisticsSklearnAdaBoostRegressor.__attributes
        self._data = self.parse_data(data)

    def parse_data(self, data):
        _data = dict()
        for attr in self.__attributes:
            for value in data:
                if hasattr(value, attr):
                    obj = getattr(value, attr, None)
                    if obj is None:
                        _data[attr] = []
                        continue

                    if attr in _data:
                        _data[attr].append(obj)
                    else:
                        _data[attr] = [obj]

                    if (d := _data[attr]) == []:
                        empty = True
                    else:
                        empty = False
                    _data[attr] = StatisticNumpy(np.array(d), empty=empty)

        return _data


class StatisticsSklearnRANSACRegressor(StatisticSklearn):

    __attributes = ("estimator_",)

    def __init__(self, data):
        self.__attributes = StatisticsSklearnRANSACRegressor.__attributes
        self._data = self.parse_data(data)

    def parse_data(self, data):
        _data = dict()

        estimator_list = list()
        for value in data:
            estimator = getattr(value, "estimator_", None)
            if estimator is None:
                break
            estimator_list.append(estimator)
            _data.update(StatisticsSklearnLinearRegression(
                estimator_list).to_dict())

        return _data


class StatisticsSklearnLinearRegression(StatisticSklearn):

    __attributes = ("coef_", "singular_", "intercept_")

    def __init__(self, data):
        self.__attributes = StatisticsSklearnLinearRegression.__attributes
        self._data = self.parse_data(data)

    def parse_data(self, data):
        _data = dict()
        for attr in self.__attributes:
            for value in data:
                if hasattr(value, attr):
                    obj = getattr(value, attr, None)
                    if obj is None:
                        _data[attr] = []
                        continue

                    if attr in _data:
                        _data[attr].append(obj)
                    else:
                        _data[attr] = [obj]

                    if (d := _data[attr]) == []:
                        empty = True
                    else:
                        empty = False
                    _data[attr] = StatisticNumpy(np.array(d), empty=empty)

        return _data
