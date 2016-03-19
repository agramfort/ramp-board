import datetime
from sklearn.cross_validation import StratifiedShuffleSplit
import databoard.scores as scores
from databoard.specific.problems.iris import problem_name  # noqa

event_name = 'iris_test'  # should be the same as the file name

# Unmutable config parameters that we always read from here

event_title = 'Iris classification (test)'

random_state = 57
cv_test_size = 0.5
n_cv = 2
score = scores.Accuracy()


def get_cv(y_train_array):
    cv = StratifiedShuffleSplit(
        y_train_array, n_iter=n_cv, test_size=cv_test_size,
        random_state=random_state)
    return cv

# Mutable config parameters to initialize database fields

max_members_per_team = 1
max_n_ensemble = 80  # max number of submissions in greedy ensemble
score_precision = 3  # n_digits
is_send_trained_mails = False
is_send_submitted_mails = False
min_duration_between_submissions = 15 * 60  # sec
opening_timestamp = datetime.datetime(2000, 1, 1, 0, 0, 0)
# before links to submissions in leaderboard are not alive
public_opening_timestamp = datetime.datetime(2000, 1, 1, 0, 0, 0)
closing_timestamp = datetime.datetime(4000, 1, 1, 0, 0, 0)
