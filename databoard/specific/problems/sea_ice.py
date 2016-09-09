import os
import sys
import numpy as np
import xarray as xr
from databoard.config import submissions_path, problems_path
import databoard.regression_prediction as prediction  # noqa

sys.path.append(os.path.dirname(os.path.abspath(submissions_path)))

problem_name = 'sea_ice'  # should be the same as the file name

workflow_name = 'ts_feature_extractor_regressor_workflow'

X_train_filename = os.path.join(
    problems_path, problem_name, 'data', 'private', 'sea_ice_X_train.nc')
y_train_filename = os.path.join(
    problems_path, problem_name, 'data', 'private', 'sea_ice_y_train.npy')
X_test_filename = os.path.join(
    problems_path, problem_name, 'data', 'private', 'sea_ice_X_test.nc')
y_test_filename = os.path.join(
    problems_path, problem_name, 'data', 'private', 'sea_ice_y_test.npy')


def prepare_data():
    pass


def get_train_data():
    X_train_ds = xr.open_dataset(X_train_filename, decode_times=False)
    y_train_array = np.load(y_train_filename)
    return X_train_ds, y_train_array


def get_test_data():
    X_test_ds = xr.open_dataset(X_test_filename, decode_times=False)
    y_test_array = np.load(y_test_filename)
    return X_test_ds, y_test_array[X_test_ds.attrs['n_burn_in']:]
