# AUTOGENERATED! DO NOT EDIT! File to edit: nbs/016_data.preprocessing.ipynb (unless otherwise specified).

__all__ = ['ToNumpyCategory', 'OneHot', 'TSNan2Value', 'Nan2Value', 'TSStandardize', 'TSNormalize', 'TSClipOutliers',
           'TSClip', 'TSRobustScale', 'TSDiff', 'TSLog', 'TSCyclicalPosition', 'TSLinearPosition', 'TSLogReturn',
           'TSAdd', 'TSShrinkDataFrame', 'TSOneHotEncoder', 'TSCategoricalEncoder', 'TSDateTimeEncoder',
           'default_date_attr', 'TSMissingnessEncoder', 'Preprocessor', 'StandardScaler', 'RobustScaler', 'Normalizer',
           'BoxCox', 'YeoJohnshon', 'Quantile', 'ReLabeler']

# Cell
from ..imports import *
from ..utils import *
from .external import *
from .core import *

# Cell
class ToNumpyCategory(Transform):
    "Categorize a numpy batch"
    order = 90

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def encodes(self, o: np.ndarray):
        self.type = type(o)
        self.cat = Categorize()
        self.cat.setup(o)
        self.vocab = self.cat.vocab
        return np.asarray(stack([self.cat(oi) for oi in o]))

    def decodes(self, o: (np.ndarray, torch.Tensor)):
        return stack([self.cat.decode(oi) for oi in o])

# Cell
class OneHot(Transform):
    "One-hot encode/ decode a batch"
    order = 90
    def __init__(self, n_classes=None, **kwargs):
        self.n_classes = n_classes
        super().__init__(**kwargs)
    def encodes(self, o: torch.Tensor):
        if not self.n_classes: self.n_classes = len(np.unique(o))
        return torch.eye(self.n_classes)[o]
    def encodes(self, o: np.ndarray):
        o = ToNumpyCategory()(o)
        if not self.n_classes: self.n_classes = len(np.unique(o))
        return np.eye(self.n_classes)[o]
    def decodes(self, o: torch.Tensor): return torch.argmax(o, dim=-1)
    def decodes(self, o: np.ndarray): return np.argmax(o, axis=-1)

# Cell
class TSNan2Value(Transform):
    "Replaces any nan values by a predefined value or median"
    order = 90
    def __init__(self, value=0, median=False, by_sample_and_var=True):
        store_attr()
        if not ismin_torch("1.8"):
            raise ValueError('This function only works with Pytorch>=1.8.')

    def encodes(self, o:TSTensor):
        mask = torch.isnan(o)
        if mask.any():
            if self.median:
                if self.by_sample_and_var:
                    median = torch.nanmedian(o, dim=2, keepdim=True)[0].repeat(1, 1, o.shape[-1])
                    o[mask] = median[mask]
                else:
                    o = torch_nan_to_num(o, torch.nanmedian(o))
        o = torch_nan_to_num(o, self.value)
        return o

Nan2Value = TSNan2Value

# Cell

class TSStandardize(Transform):
    """Standardizes batch of type `TSTensor`

    Args:
        - mean: you can pass a precalculated mean value as a torch tensor which is the one that will be used, or leave as None, in which case
            it will be estimated using a batch.
        - std: you can pass a precalculated std value as a torch tensor which is the one that will be used, or leave as None, in which case
            it will be estimated using a batch. If both mean and std values are passed when instantiating TSStandardize, the rest of arguments won't be used.
        - by_sample: if True, it will calculate mean and std for each individual sample. Otherwise based on the entire batch.
        - by_var:
            * False: mean and std will be the same for all variables.
            * True: a mean and std will be be different for each variable.
            * a list of ints: (like [0,1,3]) a different mean and std will be set for each variable on the list. Variables not included in the list
            won't be standardized.
            * a list that contains a list/lists: (like[0, [1,3]]) a different mean and std will be set for each element of the list. If multiple elements are
            included in a list, the same mean and std will be set for those variable in the sublist/s. (in the example a mean and std is determined for
            variable 0, and another one for variables 1 & 3 - the same one). Variables not included in the list won't be standardized.
        - by_step: if False, it will standardize values for each time step.
        - eps: it avoids dividing by 0
        - use_single_batch: if True a single training batch will be used to calculate mean & std. Else the entire training set will be used.
    """

    parameters, order = L('mean', 'std'), 90
    _setup = True # indicates it requires set up
    def __init__(self, mean=None, std=None, by_sample=False, by_var=False, by_step=False, eps=1e-8, use_single_batch=True, verbose=False):
        self.mean = tensor(mean) if mean is not None else None
        self.std = tensor(std) if std is not None else None
        self._setup = (mean is None or std is None) and not by_sample
        self.eps = eps
        self.by_sample, self.by_var, self.by_step = by_sample, by_var, by_step
        drop_axes = []
        if by_sample: drop_axes.append(0)
        if by_var: drop_axes.append(1)
        if by_step: drop_axes.append(2)
        self.axes = tuple([ax for ax in (0, 1, 2) if ax not in drop_axes])
        if by_var and is_listy(by_var):
            self.list_axes = tuple([ax for ax in (0, 1, 2) if ax not in drop_axes]) + (1,)
        self.use_single_batch = use_single_batch
        self.verbose = verbose
        if self.mean is not None or self.std is not None:
            pv(f'{self.__class__.__name__} mean={self.mean}, std={self.std}, by_sample={self.by_sample}, by_var={self.by_var}, by_step={self.by_step}\n', self.verbose)

    @classmethod
    def from_stats(cls, mean, std): return cls(mean, std)

    def setups(self, dl: DataLoader):
        if self._setup:
            if not self.use_single_batch:
                o = dl.dataset.__getitem__([slice(None)])[0]
            else:
                o, *_ = dl.one_batch()
            if self.by_var and is_listy(self.by_var):
                shape = torch.mean(o, dim=self.axes, keepdim=self.axes!=()).shape
                mean = torch.zeros(*shape, device=o.device)
                std = torch.ones(*shape, device=o.device)
                for v in self.by_var:
                    if not is_listy(v): v = [v]
                    mean[:, v] = torch_nanmean(o[:, v], dim=self.axes if len(v) == 1 else self.list_axes, keepdim=True)
                    std[:, v] = torch.clamp_min(torch_nanstd(o[:, v], dim=self.axes if len(v) == 1 else self.list_axes, keepdim=True), self.eps)
            else:
                mean = torch_nanmean(o, dim=self.axes, keepdim=self.axes!=())
                std = torch.clamp_min(torch_nanstd(o, dim=self.axes, keepdim=self.axes!=()), self.eps)
            self.mean, self.std = mean, std
            if len(self.mean.shape) == 0:
                pv(f'{self.__class__.__name__} mean={self.mean}, std={self.std}, by_sample={self.by_sample}, by_var={self.by_var}, by_step={self.by_step}\n',
                   self.verbose)
            else:
                pv(f'{self.__class__.__name__} mean shape={self.mean.shape}, std shape={self.std.shape}, by_sample={self.by_sample}, by_var={self.by_var}, by_step={self.by_step}\n',
                   self.verbose)
            self._setup = False
        elif self.by_sample: self.mean, self.std = torch.zeros(1), torch.ones(1)

    def encodes(self, o:TSTensor):
        if self.by_sample:
            if self.by_var and is_listy(self.by_var):
                shape = torch.mean(o, dim=self.axes, keepdim=self.axes!=()).shape
                mean = torch.zeros(*shape, device=o.device)
                std = torch.ones(*shape, device=o.device)
                for v in self.by_var:
                    if not is_listy(v): v = [v]
                    mean[:, v] = torch_nanmean(o[:, v], dim=self.axes if len(v) == 1 else self.list_axes, keepdim=True)
                    std[:, v] = torch.clamp_min(torch_nanstd(o[:, v], dim=self.axes if len(v) == 1 else self.list_axes, keepdim=True), self.eps)
            else:
                mean = torch_nanmean(o, dim=self.axes, keepdim=self.axes!=())
                std = torch.clamp_min(torch_nanstd(o, dim=self.axes, keepdim=self.axes!=()), self.eps)
            self.mean, self.std = mean, std
        return (o - self.mean) / self.std

    def decodes(self, o:TSTensor):
        if self.mean is None or self.std is None: return o
        return o * self.std + self.mean

    def __repr__(self): return f'{self.__class__.__name__}(by_sample={self.by_sample}, by_var={self.by_var}, by_step={self.by_step})'

# Cell

@patch
def mul_min(x:(torch.Tensor, TSTensor, NumpyTensor), axes=(), keepdim=False):
    if axes == (): return retain_type(x.min(), x)
    axes = reversed(sorted(axes if is_listy(axes) else [axes]))
    min_x = x
    for ax in axes: min_x, _ = min_x.min(ax, keepdim)
    return retain_type(min_x, x)


@patch
def mul_max(x:(torch.Tensor, TSTensor, NumpyTensor), axes=(), keepdim=False):
    if axes == (): return retain_type(x.max(), x)
    axes = reversed(sorted(axes if is_listy(axes) else [axes]))
    max_x = x
    for ax in axes: max_x, _ = max_x.max(ax, keepdim)
    return retain_type(max_x, x)


class TSNormalize(Transform):
    "Normalizes batch of type `TSTensor`"
    parameters, order = L('min', 'max'), 90
    _setup = True # indicates it requires set up
    def __init__(self, min=None, max=None, range=(-1, 1), by_sample=False, by_var=False, by_step=False, clip_values=True,
                 use_single_batch=True, verbose=False):
        self.min = tensor(min) if min is not None else None
        self.max = tensor(max) if max is not None else None
        self._setup = (self.min is None and self.max is None) and not by_sample
        self.range_min, self.range_max = range
        self.by_sample, self.by_var, self.by_step = by_sample, by_var, by_step
        drop_axes = []
        if by_sample: drop_axes.append(0)
        if by_var: drop_axes.append(1)
        if by_step: drop_axes.append(2)
        self.axes = tuple([ax for ax in (0, 1, 2) if ax not in drop_axes])
        if by_var and is_listy(by_var):
            self.list_axes = tuple([ax for ax in (0, 1, 2) if ax not in drop_axes]) + (1,)
        self.clip_values = clip_values
        self.use_single_batch = use_single_batch
        self.verbose = verbose
        if self.min is not None or self.max is not None:
            pv(f'{self.__class__.__name__} min={self.min}, max={self.max}, by_sample={self.by_sample}, by_var={self.by_var}, by_step={self.by_step}\n', self.verbose)

    @classmethod
    def from_stats(cls, min, max, range_min=0, range_max=1): return cls(min, max, self.range_min, self.range_max)

    def setups(self, dl: DataLoader):
        if self._setup:
            if not self.use_single_batch:
                o = dl.dataset.__getitem__([slice(None)])[0]
            else:
                o, *_ = dl.one_batch()
            if self.by_var and is_listy(self.by_var):
                shape = torch.mean(o, dim=self.axes, keepdim=self.axes!=()).shape
                _min = torch.zeros(*shape, device=o.device) + self.range_min
                _max = torch.zeros(*shape, device=o.device) + self.range_max
                for v in self.by_var:
                    if not is_listy(v): v = [v]
                    _min[:, v] = o[:, v].mul_min(self.axes if len(v) == 1 else self.list_axes, keepdim=self.axes!=())
                    _max[:, v] = o[:, v].mul_max(self.axes if len(v) == 1 else self.list_axes, keepdim=self.axes!=())
            else:
                _min, _max = o.mul_min(self.axes, keepdim=self.axes!=()), o.mul_max(self.axes, keepdim=self.axes!=())
            self.min, self.max = _min, _max
            if len(self.min.shape) == 0:
                pv(f'{self.__class__.__name__} min={self.min}, max={self.max}, by_sample={self.by_sample}, by_var={self.by_var}, by_step={self.by_step}\n',
                   self.verbose)
            else:
                pv(f'{self.__class__.__name__} min shape={self.min.shape}, max shape={self.max.shape}, by_sample={self.by_sample}, by_var={self.by_var}, by_step={self.by_step}\n',
                   self.verbose)
            self._setup = False
        elif self.by_sample: self.min, self.max = -torch.ones(1), torch.ones(1)

    def encodes(self, o:TSTensor):
        if self.by_sample:
            if self.by_var and is_listy(self.by_var):
                shape = torch.mean(o, dim=self.axes, keepdim=self.axes!=()).shape
                _min = torch.zeros(*shape, device=o.device) + self.range_min
                _max = torch.ones(*shape, device=o.device) + self.range_max
                for v in self.by_var:
                    if not is_listy(v): v = [v]
                    _min[:, v] = o[:, v].mul_min(self.axes, keepdim=self.axes!=())
                    _max[:, v] = o[:, v].mul_max(self.axes, keepdim=self.axes!=())
            else:
                _min, _max = o.mul_min(self.axes, keepdim=self.axes!=()), o.mul_max(self.axes, keepdim=self.axes!=())
            self.min, self.max = _min, _max
        output = ((o - self.min) / (self.max - self.min)) * (self.range_max - self.range_min) + self.range_min
        if self.clip_values:
            if self.by_var and is_listy(self.by_var):
                for v in self.by_var:
                    if not is_listy(v): v = [v]
                    output[:, v] = torch.clamp(output[:, v], self.range_min, self.range_max)
            else:
                output = torch.clamp(output, self.range_min, self.range_max)
        return output

    def __repr__(self): return f'{self.__class__.__name__}(by_sample={self.by_sample}, by_var={self.by_var}, by_step={self.by_step})'

# Cell
class TSClipOutliers(Transform):
    "Clip outliers batch of type `TSTensor` based on the IQR"
    parameters, order = L('min', 'max'), 90
    _setup = True # indicates it requires set up
    def __init__(self, min=None, max=None, by_sample=False, by_var=False, use_single_batch=False, verbose=False):

        self.min = tensor(min) if min is not None else tensor(-np.inf)
        self.max = tensor(max) if max is not None else tensor(np.inf)
        self.by_sample, self.by_var = by_sample, by_var
        self._setup = (min is None or max is None) and not by_sample
        if by_sample and by_var: self.axis = (2)
        elif by_sample: self.axis = (1, 2)
        elif by_var: self.axis = (0, 2)
        else: self.axis = None
        self.use_single_batch = use_single_batch
        self.verbose = verbose
        if min is not None or max is not None:
            pv(f'{self.__class__.__name__} min={min}, max={max}\n', self.verbose)

    def setups(self, dl: DataLoader):
        if self._setup:
            if not self.use_single_batch:
                o = dl.dataset.__getitem__([slice(None)])[0]
            else:
                o, *_ = dl.one_batch()
            min, max = get_outliers_IQR(o, self.axis)
            self.min, self.max = tensor(min), tensor(max)
            if self.axis is None: pv(f'{self.__class__.__name__} min={self.min}, max={self.max}, by_sample={self.by_sample}, by_var={self.by_var}\n',
                                     self.verbose)
            else: pv(f'{self.__class__.__name__} min={self.min.shape}, max={self.max.shape}, by_sample={self.by_sample}, by_var={self.by_var}\n',
                     self.verbose)
            self._setup = False

    def encodes(self, o:TSTensor):
        if self.axis is None: return torch.clamp(o, self.min, self.max)
        elif self.by_sample:
            min, max = get_outliers_IQR(o, axis=self.axis)
            self.min, self.max = o.new(min), o.new(max)
        return torch_clamp(o, self.min, self.max)

    def __repr__(self): return f'{self.__class__.__name__}(by_sample={self.by_sample}, by_var={self.by_var})'

# Cell
class TSClip(Transform):
    "Clip  batch of type `TSTensor`"
    parameters, order = L('min', 'max'), 90
    def __init__(self, min=-6, max=6):
        self.min = torch.tensor(min)
        self.max = torch.tensor(max)

    def encodes(self, o:TSTensor):
        return torch.clamp(o, self.min, self.max)
    def __repr__(self): return f'{self.__class__.__name__}(min={self.min}, max={self.max})'

# Cell
class TSRobustScale(Transform):
    r"""This Scaler removes the median and scales the data according to the quantile range (defaults to IQR: Interquartile Range)"""
    parameters, order = L('median', 'iqr'), 90
    _setup = True # indicates it requires set up
    def __init__(self, median=None, iqr=None, quantile_range=(25.0, 75.0), use_single_batch=True, eps=1e-8, verbose=False):
        self.median = tensor(median) if median is not None else None
        self.iqr = tensor(iqr) if iqr is not None else None
        self._setup = median is None or iqr is None
        self.use_single_batch = use_single_batch
        self.eps = eps
        self.verbose = verbose
        self.quantile_range = quantile_range

    def setups(self, dl: DataLoader):
        if self._setup:
            if not self.use_single_batch:
                o = dl.dataset.__getitem__([slice(None)])[0]
            else:
                o, *_ = dl.one_batch()

            new_o = o.permute(1,0,2).flatten(1)
            median = get_percentile(new_o, 50, axis=1)
            iqrmin, iqrmax = get_outliers_IQR(new_o, axis=1, quantile_range=self.quantile_range)
            self.median = median.unsqueeze(0)
            self.iqr = torch.clamp_min((iqrmax - iqrmin).unsqueeze(0), self.eps)

            pv(f'{self.__class__.__name__} median={self.median.shape} iqr={self.iqr.shape}', self.verbose)
            self._setup = False
        else:
            if self.median is None: self.median = torch.zeros(1, device=dl.device)
            if self.iqr is None: self.iqr = torch.ones(1, device=dl.device)


    def encodes(self, o:TSTensor):
        return (o - self.median) / self.iqr

    def __repr__(self): return f'{self.__class__.__name__}(quantile_range={self.quantile_range}, use_single_batch={self.use_single_batch})'

# Cell
class TSDiff(Transform):
    "Differences batch of type `TSTensor`"
    order = 90
    def __init__(self, lag=1, pad=True):
        self.lag, self.pad = lag, pad

    def encodes(self, o:TSTensor):
        return torch_diff(o, lag=self.lag, pad=self.pad)

    def __repr__(self): return f'{self.__class__.__name__}(lag={self.lag}, pad={self.pad})'

# Cell
class TSLog(Transform):
    "Log transforms batch of type `TSTensor` + 1. Accepts positive and negative numbers"
    order = 90
    def __init__(self, ex=None, **kwargs):
        self.ex = ex
        super().__init__(**kwargs)
    def encodes(self, o:TSTensor):
        output = torch.zeros_like(o)
        output[o > 0] = torch.log1p(o[o > 0])
        output[o < 0] = -torch.log1p(torch.abs(o[o < 0]))
        if self.ex is not None: output[...,self.ex,:] = o[...,self.ex,:]
        return output
    def decodes(self, o:TSTensor):
        output = torch.zeros_like(o)
        output[o > 0] = torch.exp(o[o > 0]) - 1
        output[o < 0] = -torch.exp(torch.abs(o[o < 0])) + 1
        if self.ex is not None: output[...,self.ex,:] = o[...,self.ex,:]
        return output
    def __repr__(self): return f'{self.__class__.__name__}()'

# Cell
class TSCyclicalPosition(Transform):
    """Concatenates the position along the sequence as 2 additional variables (sine and cosine)

        Args:
            magnitude: added for compatibility. It's not used.
    """
    order = 90
    def __init__(self, magnitude=None, **kwargs):
        super().__init__(**kwargs)

    def encodes(self, o: TSTensor):
        bs,_,seq_len = o.shape
        sin, cos = sincos_encoding(seq_len, device=o.device)
        output = torch.cat([o, sin.reshape(1,1,-1).repeat(bs,1,1), cos.reshape(1,1,-1).repeat(bs,1,1)], 1)
        return output

# Cell

class TSLinearPosition(Transform):
    """Concatenates the position along the sequence as 1 additional variable

        Args:
            magnitude: added for compatibility. It's not used.
    """

    order = 90
    def __init__(self, magnitude=None, lin_range=(-1,1), **kwargs):
        self.lin_range = lin_range
        super().__init__(**kwargs)

    def encodes(self, o: TSTensor):
        bs,_,seq_len = o.shape
        lin = linear_encoding(seq_len, device=o.device, lin_range=self.lin_range)
        output = torch.cat([o, lin.reshape(1,1,-1).repeat(bs,1,1)], 1)
        return output

# Cell
class TSLogReturn(Transform):
    "Calculates log-return of batch of type `TSTensor`. For positive values only"
    order = 90
    def __init__(self, lag=1, pad=True):
        self.lag, self.pad = lag, pad

    def encodes(self, o:TSTensor):
        return torch_diff(torch.log(o), lag=self.lag, pad=self.pad)

    def __repr__(self): return f'{self.__class__.__name__}(lag={self.lag}, pad={self.pad})'

# Cell
class TSAdd(Transform):
    "Add a defined amount to each batch of type `TSTensor`."
    order = 90
    def __init__(self, add):
        self.add = add

    def encodes(self, o:TSTensor):
        return torch.add(o, self.add)
    def __repr__(self): return f'{self.__class__.__name__}(lag={self.lag}, pad={self.pad})'

# Cell
from sklearn.base import BaseEstimator, TransformerMixin
from fastai.data.transforms import CategoryMap
from joblib import dump, load


class TSShrinkDataFrame(BaseEstimator, TransformerMixin):

    def __init__(self, columns=None, skip=[], obj2cat=True, int2uint=False, verbose=True):
        self.columns, self.skip, self.obj2cat, self.int2uint, self.verbose = listify(columns), skip, obj2cat, int2uint, verbose

    def fit(self, X:pd.DataFrame, y=None, **fit_params):
        assert isinstance(X, pd.DataFrame)
        self.old_dtypes = X.dtypes
        if not self.columns: self.columns = X.columns
        self.dt = df_shrink_dtypes(X[self.columns], self.skip, obj2cat=self.obj2cat, int2uint=self.int2uint)
        return self

    def transform(self, X:pd.DataFrame, y=None, **transform_params):
        assert isinstance(X, pd.DataFrame)
        if self.verbose:
            start_memory = X.memory_usage().sum() / 1024**2
            print(f"Memory usage of dataframe is {start_memory} MB")
        X[self.columns] = X[self.columns].astype(self.dt)
        if self.verbose:
            end_memory = X.memory_usage().sum() / 1024**2
            print(f"Memory usage of dataframe after reduction {end_memory} MB")
            print(f"Reduced by {100 * (start_memory - end_memory) / start_memory} % ")
        return X

    def inverse_transform(self, X):
        assert isinstance(X, pd.DataFrame)
        if self.verbose:
            start_memory = X.memory_usage().sum() / 1024**2
            print(f"Memory usage of dataframe is {start_memory} MB")
        X = X.astype(self.old_dtypes)
        if self.verbose:
            end_memory = X.memory_usage().sum() / 1024**2
            print(f"Memory usage of dataframe after reduction {end_memory} MB")
            print(f"Reduced by {100 * (start_memory - end_memory) / start_memory} % ")
        return X


# Cell
class TSOneHotEncoder(BaseEstimator, TransformerMixin):

    def __init__(self, columns=None, drop=True, add_na=True, dtype=np.int64):
        self.columns = listify(columns)
        self.drop, self.add_na, self.dtype = drop, add_na, dtype


    def fit(self, X:pd.DataFrame, y=None, **fit_params):
        assert isinstance(X, pd.DataFrame)
        if not self.columns: self.columns = X.columns
        handle_unknown = "ignore" if self.add_na else "error"
        self.ohe_tfm = sklearn.preprocessing.OneHotEncoder(handle_unknown=handle_unknown)
        if len(self.columns) == 1:
            self.ohe_tfm.fit(X[self.columns].to_numpy().reshape(-1, 1))
        else:
            self.ohe_tfm.fit(X[self.columns])
        return self

    def transform(self, X:pd.DataFrame, y=None, **transform_params):
        assert isinstance(X, pd.DataFrame)
        if len(self.columns) == 1:
            output = self.ohe_tfm.transform(X[self.columns].to_numpy().reshape(-1, 1)).toarray().astype(self.dtype)
        else:
            output = self.ohe_tfm.transform(X[self.columns]).toarray().astype(self.dtype)
        new_cols = []
        for i,col in enumerate(self.columns):
            for cats in self.ohe_tfm.categories_[i]:
                new_cols.append(f"{str(col)}_{str(cats)}")
        X[new_cols] = output
        if self.drop: X = X.drop(self.columns, axis=1)
        return X


# Cell
class TSCategoricalEncoder(BaseEstimator, TransformerMixin):

    def __init__(self, columns=None, add_na=True):
        self.columns = listify(columns)
        self.add_na = add_na

    def fit(self, X:pd.DataFrame, y=None, **fit_params):
        assert isinstance(X, pd.DataFrame)
        if not self.columns: self.columns = X.columns
        self.cat_tfms = []
        for column in self.columns:
            self.cat_tfms.append(CategoryMap(X[column], add_na=self.add_na))
        return self

    def transform(self, X:pd.DataFrame, y=None, **transform_params):
        assert isinstance(X, pd.DataFrame)
        for cat_tfm, column in zip(self.cat_tfms, self.columns):
            X[column] = cat_tfm.map_objs(X[column])
        return X

    def inverse_transform(self, X):
        assert isinstance(X, pd.DataFrame)
        for cat_tfm, column in zip(self.cat_tfms, self.columns):
            X[column] = cat_tfm.map_ids(X[column])
        return X

# Cell
default_date_attr = ['Year', 'Month', 'Week', 'Day', 'Dayofweek', 'Dayofyear', 'Is_month_end', 'Is_month_start',
                     'Is_quarter_end', 'Is_quarter_start', 'Is_year_end', 'Is_year_start']

class TSDateTimeEncoder(BaseEstimator, TransformerMixin):

    def __init__(self, datetime_columns=None, prefix=None, drop=True, time=False, attr=default_date_attr):
        self.datetime_columns = listify(datetime_columns)
        self.prefix, self.drop, self.time, self.attr = prefix, drop, time ,attr

    def fit(self, X:pd.DataFrame, y=None, **fit_params):
        assert isinstance(X, pd.DataFrame)
        if self.time: self.attr = self.attr + ['Hour', 'Minute', 'Second']
        if not self.datetime_columns:
            self.datetime_columns = X.columns
        self.prefixes = []
        for dt_column in self.datetime_columns:
            self.prefixes.append(re.sub('[Dd]ate$', '', dt_column) if self.prefix is None else self.prefix)
        return self

    def transform(self, X:pd.DataFrame, y=None, **transform_params):
        assert isinstance(X, pd.DataFrame)

        for dt_column,prefix in zip(self.datetime_columns,self.prefixes):
            make_date(X, dt_column)
            field = X[dt_column]

            # Pandas removed `dt.week` in v1.1.10
            week = field.dt.isocalendar().week.astype(field.dt.day.dtype) if hasattr(field.dt, 'isocalendar') else field.dt.week
            for n in self.attr: X[prefix + "_" + n] = getattr(field.dt, n.lower()) if n != 'Week' else week
            if self.drop: X = X.drop(self.datetime_columns, axis=1)
        return X

# Cell
class TSMissingnessEncoder(BaseEstimator, TransformerMixin):

    def __init__(self, columns=None):
        self.columns = listify(columns)

    def fit(self, X:pd.DataFrame, y=None, **fit_params):
        assert isinstance(X, pd.DataFrame)
        if not self.columns: self.columns = X.columns
        self.missing_columns = [f"{cn}_missing" for cn in self.columns]
        return self

    def transform(self, X:pd.DataFrame, y=None, **transform_params):
        assert isinstance(X, pd.DataFrame)
        X[self.missing_columns] = X[self.columns].isnull().astype(int)
        return X

    def inverse_transform(self, X):
        assert isinstance(X, pd.DataFrame)
        X.drop(self.missing_columns, axis=1, inplace=True)
        return X

# Cell
class Preprocessor():
    def __init__(self, preprocessor, **kwargs):
        self.preprocessor = preprocessor(**kwargs)

    def fit(self, o):
        if isinstance(o, pd.Series): o = o.values.reshape(-1,1)
        else: o = o.reshape(-1,1)
        self.fit_preprocessor = self.preprocessor.fit(o)
        return self.fit_preprocessor

    def transform(self, o, copy=True):
        if type(o) in [float, int]: o = array([o]).reshape(-1,1)
        o_shape = o.shape
        if isinstance(o, pd.Series): o = o.values.reshape(-1,1)
        else: o = o.reshape(-1,1)
        output = self.fit_preprocessor.transform(o).reshape(*o_shape)
        if isinstance(o, torch.Tensor): return o.new(output)
        return output

    def inverse_transform(self, o, copy=True):
        o_shape = o.shape
        if isinstance(o, pd.Series): o = o.values.reshape(-1,1)
        else: o = o.reshape(-1,1)
        output = self.fit_preprocessor.inverse_transform(o).reshape(*o_shape)
        if isinstance(o, torch.Tensor): return o.new(output)
        return output


StandardScaler = partial(sklearn.preprocessing.StandardScaler)
setattr(StandardScaler, '__name__', 'StandardScaler')
RobustScaler = partial(sklearn.preprocessing.RobustScaler)
setattr(RobustScaler, '__name__', 'RobustScaler')
Normalizer = partial(sklearn.preprocessing.MinMaxScaler, feature_range=(-1, 1))
setattr(Normalizer, '__name__', 'Normalizer')
BoxCox = partial(sklearn.preprocessing.PowerTransformer, method='box-cox')
setattr(BoxCox, '__name__', 'BoxCox')
YeoJohnshon = partial(sklearn.preprocessing.PowerTransformer, method='yeo-johnson')
setattr(YeoJohnshon, '__name__', 'YeoJohnshon')
Quantile = partial(sklearn.preprocessing.QuantileTransformer, n_quantiles=1_000, output_distribution='normal', random_state=0)
setattr(Quantile, '__name__', 'Quantile')

# Cell
def ReLabeler(cm):
    r"""Changes the labels in a dataset based on a dictionary (class mapping)
        Args:
            cm = class mapping dictionary
    """
    def _relabel(y):
        obj = len(set([len(listify(v)) for v in cm.values()])) > 1
        keys = cm.keys()
        if obj:
            new_cm = {k:v for k,v in zip(keys, [listify(v) for v in cm.values()])}
            return np.array([new_cm[yi] if yi in keys else listify(yi) for yi in y], dtype=object).reshape(*y.shape)
        else:
            new_cm = {k:v for k,v in zip(keys, [listify(v) for v in cm.values()])}
            return np.array([new_cm[yi] if yi in keys else listify(yi) for yi in y]).reshape(*y.shape)
    return _relabel