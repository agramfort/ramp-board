import os
import zlib
import hashlib
import logging
import datetime
import numpy as np
from flask import request
from sqlalchemy.ext.hybrid import hybrid_property

from databoard import db
import databoard.config as config
import databoard.generic as generic

# Training set table
# Problem table
# Ramp table that connects all (training set, problem, cv, specific)
# specific should be cut at least into problem-specific, data and cv-specific,
# and ramp (event) specific files

logger = logging.getLogger('databoard')


class NumpyType(db.TypeDecorator):
    """ Storing zipped numpy arrays."""
    impl = db.LargeBinary

    def process_bind_param(self, value, dialect):
        # we convert the initial value into np.array to handle None and lists
        return zlib.compress(np.array(value).dumps())

    def process_result_value(self, value, dialect):
        return np.loads(zlib.decompress(value))


class ScoreType(db.TypeDecorator):
    """ Storing score types (with redefined comparators)."""
    impl = db.Float

    # going into the db
    def process_bind_param(self, value, dialect):
        return float(value)

    # going out of the db
    def process_result_value(self, value, dialect):
        return config.config_object.specific.score.convert(value)


class PredictionType(db.TypeDecorator):
    """ Storing Predictions."""
    impl = db.LargeBinary

    def process_bind_param(self, value, dialect):
        # we convert the initial value into np.array to handle None and lists
        if value is None:
            return None
        return zlib.compress(np.array(value.y_pred).dumps())

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        specific = config.config_object.specific
        return specific.Predictions(y_pred=np.loads(zlib.decompress(value)))


class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(20), nullable=False, unique=True)
    hashed_password = db.Column(db.String, nullable=False)
    lastname = db.Column(db.String, nullable=False)
    firstname = db.Column(db.String, nullable=False)
    email = db.Column(db.String, nullable=False, unique=True)
    linkedin_url = db.Column(db.String, default=None)
    twitter_url = db.Column(db.String, default=None)
    facebook_url = db.Column(db.String, default=None)
    google_url = db.Column(db.String, default=None)
    hidden_notes = db.Column(db.String, default=None)
    is_want_news = db.Column(db.Boolean, default=True)
    access_level = db.Column(db.Enum(
        'admin', 'user', 'asked'), default='asked')  # 'asked' needs approval
    signup_timestamp = db.Column(db.DateTime, nullable=False)

    # Flask-Login fields
    is_authenticated = db.Column(db.Boolean, default=True)
    is_active = db.Column(db.Boolean, default=True)

    def __init__(self, name, hashed_password, lastname, firstname, email,
                 access_level='user', hidden_notes=''):
        self.name = name
        self.hashed_password = hashed_password
        self.lastname = lastname
        self.firstname = firstname
        self.email = email
        self.access_level = access_level
        self.hidden_notes = hidden_notes
        self.signup_timestamp = datetime.datetime.utcnow()

    @property
    def is_anonymous(self):
        return False

    def get_id(self):
        try:
            return unicode(self.id)  # python 2
        except NameError:
            return str(self.id)  # python 3

    def __str__(self):
        str_ = 'User({})'.format(self.name)
#        str_ = 'User({}, admined=['.format(self.name)
#        str_ += string.join([team.name for team in self.admined_teams], ', ')
#        str_ += '])'
        return str_

    def __repr__(self):
        repr = '''User(name={}, lastname={}, firstname={}, email={},
                  admined_teams={})'''.format(
            self.name, self.lastname, self.firstname, self.email,
            self.admined_teams)
        return repr


class Team(db.Model):
    __tablename__ = 'teams'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(20), nullable=False, unique=True)

    admin_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    admin = db.relationship('User', backref=db.backref('admined_teams'))

    # initiator asks for merge, acceptor accepts
    initiator_id = db.Column(
        db.Integer, db.ForeignKey('teams.id'), default=None)
    initiator = db.relationship(
        'Team', primaryjoin=('Team.initiator_id == Team.id'), uselist=False)

    acceptor_id = db.Column(
        db.Integer, db.ForeignKey('teams.id'), default=None)
    acceptor = db.relationship(
        'Team', primaryjoin=('Team.acceptor_id == Team.id'), uselist=False)

    creation_timestamp = db.Column(db.DateTime, nullable=False)
    is_active = db.Column(db.Boolean, default=True)  # ->ramp_teams

    last_submission_name = db.Column(db.String, default=None)

    def __init__(self, name, admin, initiator=None, acceptor=None):
        self.name = name
        self.admin = admin
        self.initiator = initiator
        self.acceptor = acceptor
        self.creation_timestamp = datetime.datetime.utcnow()

    def __str__(self):
        str_ = 'Team({})'.format(self.name)
        return str_

    def __repr__(self):
        repr = '''Team(name={}, admin_name={}, is_active={},
                  initiator={}, acceptor={})'''.format(
            self.name, self.admin.name, self.is_active, self.initiator,
            self.acceptor)
        return repr


def get_team_members(team):
    if team.initiator is not None:
        # "yield from" in Python 3.3
        for member in get_team_members(team.initiator):
            yield member
        for member in get_team_members(team.acceptor):
            yield member
    else:
        yield team.admin


def get_n_team_members(team):
    return len(list(get_team_members(team)))


def get_user_teams(user):
    teams = Team.query.all()
    for team in teams:
        if user in get_team_members(team):
            yield team


def get_active_user_team(user):
    teams = Team.query.all()
    for team in teams:
        if user in get_team_members(team) and team.is_active:
            return team


def get_n_user_teams(user):
    return len(get_user_teams(user))


class SubmissionFileType(db.Model):
    __tablename__ = 'submission_file_types'

    id = db.Column(db.Integer, primary_key=True)
    # eg. 'code', 'text', 'data'
    name = db.Column(db.String, nullable=False, unique=True)
    is_editable = db.Column(db.Boolean, default=True)
    max_size = db.Column(db.Integer, default=None)


class Extension(db.Model):
    __tablename__ = 'extensions'

    id = db.Column(db.Integer, primary_key=True)
    # eg. 'py', 'csv', 'R'
    name = db.Column(db.String, nullable=False, unique=True)


# many-to-many connection between SubmissionFileType and Extension
class SubmissionFileTypeExtension(db.Model):
    __tablename__ = 'submission_file_type_extensions'

    id = db.Column(db.Integer, primary_key=True)

    type_id = db.Column(
        db.Integer, db.ForeignKey('submission_file_types.id'), nullable=False)
    type = db.relationship(
        'SubmissionFileType', backref=db.backref('extensions'))

    extension_id = db.Column(
        db.Integer, db.ForeignKey('extensions.id'), nullable=False)
    extension = db.relationship(
        'Extension', backref=db.backref('submission_file_types'))

    db.UniqueConstraint(type_id, extension_id, name='we_constraint')

    @property
    def file_type(self):
        return self.type.name

    @property
    def extension_name(self):
        return self.extension.name


class WorkflowElementType(db.Model):
    __tablename__ = 'workflow_element_types'

    id = db.Column(db.Integer, primary_key=True)
    # file name without extension
    # eg, regressor, classifier, external_data
    name = db.Column(db.String, nullable=False, unique=True)

    # eg, code, text, data
    type_id = db.Column(
        db.Integer, db.ForeignKey('submission_file_types.id'), nullable=False)
    type = db.relationship(
        'SubmissionFileType', backref=db.backref('workflow_element_types'))

    def __repr__(self):
        repr = 'WorkflowElementType(name={}, type={}, is_editable={}, max_size={})'.format(
            self.name, self.type.name, self.type.is_editable,
            self.type.max_size)
        return repr

    @property
    def file_type(self):
        return self.type.name

    @property
    def is_editable(self):
        return self.type.is_editable

    @property
    def max_size(self):
        return self.type.max_size


# RAMP or problem id should come in here. Or even better: workflow id which
# will then belong to RAMP or problem.
# In lists we will order files according to their ids
class WorkflowElement(db.Model):
    __tablename__ = 'workflow_elements'

    id = db.Column(db.Integer, primary_key=True)
    # Normally name will be the same as workflow_element_type.type.name,
    # unless specified otherwise. It's because in more complex workflows
    # the same type can occur more then once. self.type below will always
    # refer to workflow_element_type.type.name
    name = db.Column(db.String, nullable=False, unique=True)

    workflow_element_type_id = db.Column(
        db.Integer, db.ForeignKey('workflow_element_types.id'),
        nullable=False)
    workflow_element_type = db.relationship(
        'WorkflowElementType', backref=db.backref('submission_files'))

    def __init__(self, name, name_in_workflow=None):
        self.workflow_element_type = WorkflowElementType.query.filter_by(
            name=name).one()
        if name_in_workflow is None:
            self.name = name
        else:
            self.name = name_in_workflow

    # e.g. 'regression', 'external_data'. Normally == name
    @property
    def type(self):
        return self.workflow_element_type.name

    @property
    def file_type(self):
        return self.workflow_element_type.file_type

    @property
    def is_editable(self):
        return self.workflow_element_type.is_editable

    @property
    def max_size(self):
        return self.workflow_element_type.max_size


# TODO: we should have a SubmissionWorkflowElementType table, describing the
# type of files we are expecting for a given RAMP. Fast unit test should be
# set up there, and each file should be unit tested right after submission.
# Kozmetics: erhaps mark which file the leaderboard link should point to (right
# now it is set to the first file in the list which is arbitrary).
# We will also have to handle auxiliary files (like csvs or other classes).
# User interface could have a sinlge submission form with a menu containing
# the file names for a given ramp + an "other" field when users will have to
# name their files
class SubmissionFile(db.Model):
    __tablename__ = 'submission_files'

    id = db.Column(db.Integer, primary_key=True)
    submission_id = db.Column(
        db.Integer, db.ForeignKey('submissions.id'), nullable=False)
    submission = db.relationship(
        'Submission',
        backref=db.backref('files', cascade="all, delete-orphan"))

    # e.g. 'regression', 'external_data'
    workflow_element_id = db.Column(
        db.Integer, db.ForeignKey('workflow_elements.id'),
        nullable=False)
    workflow_element = db.relationship(
        'WorkflowElement', backref=db.backref('submission_files'))

    # e.g., ('code', 'py'), ('data', 'csv')
    submission_file_type_extension_id = db.Column(
        db.Integer, db.ForeignKey('submission_file_type_extensions.id'),
        nullable=False)
    submission_file_type_extension = db.relationship(
        'SubmissionFileTypeExtension', backref=db.backref('submission_files'))

    # eg, 'py'
    @property
    def is_editable(self):
        return self.workflow_element.is_editable

    # eg, 'py'
    @property
    def extension(self):
        return self.submission_file_type_extension.extension.name

    # eg, 'regressor'
    @property
    def type(self):
        return self.workflow_element.type

    # eg, 'regressor', Normally same as type, except when type appears more
    # than once in workflow
    @property
    def name(self):
        return self.workflow_element.name

    # Complete file name, eg, 'regressor.py'
    @property
    def f_name(self):
        return self.type + '.' + self.extension

    @property
    def path(self):
        return self.submission.path + os.path.sep + self.f_name

    def get_code(self):
        with open(self.path) as f:
            code = f.read()
        return code

    def set_code(self, code):
        code.encode('ascii')  # to raise an exception if code is not ascii
        with open(self.path, 'w') as f:
            f.write(code)

    def __repr__(self):
        return 'SubmissionFile(name={}, type={}, extension={}, path={})'.format(
            self.name, self.type, self.extension, self.path)


def combine_predictions_list(predictions_list, index_list=None):
    """Combines predictions by taking the mean of their
    get_combineable_predictions views. E.g. for regression it is the actual
    predictions, and for classification it is the probability array (which
    should be calibrated if we want the best performance). Called both for
    combining one submission on cv folds (a single model that is trained on
    different folds) and several models on a single fold.
    Called by
    _get_bagging_score : which combines bags of the same model, trained on
        different folds, on the heldout test set
    _get_cv_bagging_score : which combines cv-bags of the same model, trained
        on different folds, on the training set
    get_next_best_single_fold : which does one step of the greedy forward
        selection (of different models) on a single fold
    _get_combined_predictions_single_fold : which does the full loop of greedy
        forward selection (of different models), until improvement, on a single
        fold
    _get_combined_test_predictions_single_fold : which computes the combination
        (constructed on the cv valid set) on the holdout test set, on a single
        fold
    _get_combined_test_predictions : which combines the foldwise combined
        and foldwise best test predictions into a single megacombination

    Parameters
    ----------
    predictions_list : list of instances of Predictions
        Each element of the list is an instance of Predictions of a given model
        on the same data points.
    index_list : None | list of integers
        The subset of predictions to be combined. If None, the full set is
        combined.

    Returns
    -------
    combined_predictions : instance of Predictions
        A predictions instance containing the combined (averaged) predictions.
    """
    specific = config.config_object.specific

    if index_list is None:  # we combine the full list
        index_list = range(len(predictions_list))

    y_comb_list = np.array(
        [predictions_list[i].y_pred_comb for i in index_list])

    y_comb = np.nanmean(y_comb_list, axis=0)
    combined_predictions = specific.Predictions(y_pred=y_comb)
    return combined_predictions


def _get_score_cv_bags(predictions_list, true_predictions, test_is_list=None):
    specific = config.config_object.specific

    if test_is_list is None:  # we combine the full list
        test_is_list = [range(len(predictions.y_pred))
                        for predictions in predictions_list]

    n_samples = true_predictions.n_samples
    y_comb = np.array([specific.Predictions(n_samples=n_samples)
                       for _ in predictions_list])
    score_cv_bags = []
    for i, test_is in enumerate(test_is_list):
        y_comb[i].set_valid_in_train(predictions_list[i], test_is)
        combined_predictions = combine_predictions_list(y_comb[:i + 1])
        valid_indexes = combined_predictions.valid_indexes
        score_cv_bags.append(specific.score(
            true_predictions, combined_predictions, valid_indexes))
        # XXX maybe use masked arrays rather than passing valid_indexes
    return score_cv_bags


# evaluate right after train/test, so no need for 'scored' states
submission_states = db.Enum(
    'new', 'checked', 'checking_error', 'trained', 'training_error',
    'validated', 'validating_error', 'tested', 'testing_error')


class Submission(db.Model):
    """An abstract (untrained) submission."""

    __tablename__ = 'submissions'

    id = db.Column(db.Integer, primary_key=True)

    team_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=False)
    # one-to-many, ->ramp_teams
    team = db.relationship('Team', backref=db.backref('submissions'))

    name = db.Column(db.String(20, convert_unicode=True), nullable=False)
    hash_ = db.Column(db.String, nullable=False)
    submission_timestamp = db.Column(db.DateTime, nullable=False)
    training_timestamp = db.Column(db.DateTime)

    # These are cv-bagged scores. Individual scores are found in
    # SubmissionToTrain
    valid_score_cv_bag = db.Column(ScoreType, default=0.0)  # cv
    test_score_cv_bag = db.Column(ScoreType, default=0.0)  # holdout
    # we store the partial scores so to see the saturation and
    # overfitting as the number of cv folds grow
    valid_score_cv_bags = db.Column(NumpyType, default=None)
    test_score_cv_bags = db.Column(NumpyType, default=None)

    contributivity = db.Column(db.Float, default=0.0)

    state = db.Column(submission_states, default='new')
    error_msg = db.Column(db.String, default='')
    # user can delete but we keep
    is_valid = db.Column(db.Boolean, default=True)
    # We can forget bad models.
    # If false, don't combine and set contributivity to zero
    is_to_ensemble = db.Column(db.Boolean, default=True)
    notes = db.Column(db.String, default='')  # eg, why is it disqualified

    # later also ramp_id
    db.UniqueConstraint(team_id, name, name='ts_constraint')

    def __init__(self, name, team):
        self.name = name
        self.team = team
        sha_hasher = hashlib.sha1()
        sha_hasher.update(self.team.name.encode('utf-8'))
        sha_hasher.update(self.name.encode('utf-8'))
        # We considered using the id, but then it will be given away in the
        # url which is maybe not a good idea.
        self.hash_ = 'm{}'.format(sha_hasher.hexdigest())
        self.submission_timestamp = datetime.datetime.utcnow()

    def __str__(self):
        return 'Submission({}/{})'.format(self.team.name, self.name)

    def __repr__(self):
        repr = '''Submission(team_name={}, name={}, files={},
                  state={}, train_time={})'''.format(
            self.team.name, self.name, self.files,
            self.state, self.train_time_cv_mean)
        return repr

    @hybrid_property
    def is_error(self):
        return (self.state == 'training_error') |\
            (self.state == 'checking_error') |\
            (self.state == 'validating_error') |\
            (self.state == 'testing_error')

    @hybrid_property
    def is_public_leaderboard(self):
        return self.is_valid & (
            (self.state == 'validated') |
            (self.state == 'tested'))

    @hybrid_property
    def is_private_leaderboard(self):
        return self.is_valid & (self.state == 'tested')

    @property
    def path(self):
        path = os.path.join(
            config.submissions_path, self.team.name, self.hash_)
        return path

    @property
    def module(self):
        return self.path.lstrip('./').replace('/', '.')

    @property
    def f_names(self):
        return [file.f_name for file in self.files]

    @property
    def name_with_link(self):
        # TODO: file order!
        return '<a href="' + self.files[0].path + '">' + self.name[:20] +\
            '</a>'

    @property
    def state_with_link(self):
        return '<a href="' + self.path + os.path.sep + 'error.txt"' + '>' +\
            self.state + '</a>'

    @property
    def train_score_cv_mean(self):
        return np.array([ts.train_score for ts in self.on_cv_folds]).mean()

    @property
    def valid_score_cv_mean(self):
        return np.array([ts.valid_score for ts in self.on_cv_folds]).mean()

    @property
    def test_score_cv_mean(self):
        return np.array([ts.test_score for ts in self.on_cv_folds]).mean()

    @property
    def train_time_cv_mean(self):
        return np.array([ts.train_time for ts in self.on_cv_folds]).mean()

    @property
    def valid_time_cv_mean(self):
        return np.array([ts.valid_time for ts in self.on_cv_folds]).mean()

    @property
    def test_time_cv_mean(self):
        return np.array(
            [ts.test_time for ts in self.submission_on_cv_folds]).mean()

    def set_state(self, state):
        self.state = state
        for submission_on_cv_fold in self.on_cv_folds:
            submission_on_cv_fold.state = state

    def get_paths(self, submissions_path=config.submissions_path):
        team_path = os.path.join(submissions_path, self.team.name)
        submission_path = os.path.join(team_path, self.hash_)
        return team_path, submission_path

    def compute_valid_score_cv_bag(self):
        """Cv-bags cv_fold.valid_predictions using combine_predictions_list.
        The predictions in predictions_list[i] belong to those indicated
        by self.on_cv_folds[i].test_is.
        """
        specific = config.config_object.specific
        true_predictions_train = generic.get_true_predictions_train()

        if self.is_public_leaderboard:
            predictions_list = [submission_on_cv_fold.valid_predictions for
                                submission_on_cv_fold in self.on_cv_folds]
            test_is_list = [submission_on_cv_fold.cv_fold.test_is for
                            submission_on_cv_fold in self.on_cv_folds]
            self.valid_score_cv_bags = _get_score_cv_bags(
                predictions_list, true_predictions_train, test_is_list)
            self.valid_score_cv_bag = self.valid_score_cv_bags[-1]
        else:
            self.valid_score_cv_bag = specific.score.zero
            self.valid_score_cv_bags = None
        db.session.commit()

    def compute_test_score_cv_bag(self):
        """Bags cv_fold.test_predictions using combine_predictions_list, and
        stores the score of the bagged predictor in test_score_cv_bag. The
        scores of partial combinations are stored in test_score_cv_bags.
        This is for assessing the bagging learning curve, which is useful for
        setting the number of cv folds to its optimal value (in case the RAMP
        is competitive, say, to win a Kaggle challenge; although it's kinda
        stupid since in those RAMPs we don't have a test file, so the learning
        curves should be assessed in compute_valid_score_cv_bag on the
        (cross-)validation sets).
        """
        specific = config.config_object.specific

        if self.is_private_leaderboard:
            # When we have submission id in Predictions, we should get the
            # team and submission from the db
            true_predictions = generic.get_true_predictions_test()
            predictions_list = [submission_on_cv_fold.test_predictions for
                                submission_on_cv_fold in self.on_cv_folds]
            combined_predictions_list = [
                combine_predictions_list(predictions_list[:i + 1]) for
                i in range(len(predictions_list))]
            self.test_score_cv_bags = [
                specific.score(true_predictions, combined_predictions) for
                combined_predictions in combined_predictions_list]
            self.test_score_cv_bag = self.test_score_cv_bags[-1]
        else:
            self.test_score_cv_bag = specific.score.zero
            self.test_score_cv_bags = None
        db.session.commit()

    # contributivity could be a property but then we could not query on it
    def set_contributivity(self):
        self.contributivity = 0.0
        if self.is_public_leaderboard:
            # we share a unit of 1. among folds
            unit_contributivity = 1. / len(self.on_cv_folds)
            for submission_on_cv_fold in self.on_cv_folds:
                self.contributivity +=\
                    unit_contributivity * submission_on_cv_fold.contributivity
        db.session.commit()

    def set_state_after_training(self):
        self.training_timestamp = datetime.datetime.utcnow()
        states = [submission_on_cv_fold.state
                  for submission_on_cv_fold in self.on_cv_folds]
        if all(state in ['tested'] for state in states):
            self.state = 'tested'
        elif all(state in ['tested', 'validated'] for state in states):
            self.state = 'validated'
        elif all(state in ['tested', 'validated', 'trained']
                 for state in states):
            self.state = 'trained'
        elif any(state == 'training_error' for state in states):
            self.state = 'training_error'
            i = states.index('training_error')
            self.error_msg = self.on_cv_folds[i].error_msg
        elif any(state == 'validating_error' for state in states):
            self.state = 'validating_error'
            i = states.index('validating_error')
            self.error_msg = self.on_cv_folds[i].error_msg
        elif any(state == 'testing_error' for state in states):
            self.state = 'testing_error'
            i = states.index('testing_error')
            self.error_msg = self.on_cv_folds[i].error_msg
        if 'error' not in self.state:
            self.error_msg = ''


def get_next_best_single_fold(predictions_list, true_predictions,
                              best_index_list):
    """Finds the model that minimizes the score if added to
    predictions_list[best_index_list]. If there is no model improving the input
    combination, the input best_index_list is returned. Otherwise the best
    model is added to the list. We could also return the combined prediction
    (for efficiency, so the combination would not have to be done each time;
    right now the algo is quadratic), but I don't think any meaningful
    rule will be associative, in which case we should redo the combination from
    scratch each time the set changes. Since now combination = mean, we could
    maintain the sum and the number of models, but it would be a bit bulky.
    We'll see how this evolves.

    Parameters
    ----------
    predictions_list : list of instances of Predictions
        Each element of the list is an instance of Predictions of a model
        on the same (cross-validation valid) data points.
    true_predictions : instance of Predictions
        The ground truth.
    best_index_list : list of integers
        Indices of the current best model.

    Returns
    -------
    best_index_list : list of integers
        Indices of the models in the new combination. If the same as input,
        no models wer found improving the score.
    """
    specific = config.config_object.specific

    best_predictions = combine_predictions_list(
        predictions_list, index_list=best_index_list)
    best_score = specific.score(true_predictions, best_predictions)
    best_index = -1
    # Combination with replacement, what Caruana suggests. Basically, if a
    # model is added several times, it's upweighted, leading to
    # integer-weighted ensembles
    for i in range(len(predictions_list)):
        combined_predictions = combine_predictions_list(
            predictions_list, index_list=np.append(best_index_list, i))
        new_score = specific.score(true_predictions, combined_predictions)
        # new_score = specific.score(pred_true, pred_comb)
        # '>' is overloaded in score, so 'x > y' means 'x is better than y'
        if new_score > best_score:
            best_predictions = combined_predictions
            best_index = i
            best_score = new_score
    if best_index > -1:
        return np.append(best_index_list, best_index), best_score
    else:
        return best_index_list, best_score


class CVFold(db.Model):
    """Created when the ramp is set up. Storing train and test folds, more
    precisely: train and test indices. Should be related to the data set
    and the ramp (that defines the cv). """

    __tablename__ = 'cv_folds'

    id = db.Column(db.Integer, primary_key=True)
    train_is = db.Column(NumpyType, nullable=False)
    test_is = db.Column(NumpyType, nullable=False)

    def __repr__(self):
        return 'fold {}'.format(self.train_is)[:15]


# TODO: rename submission to workflow and submitted file to workflow_element
# TODO: SubmissionOnCVFold should actually be a workflow element. Saving
# train_pred means that we can input it to the next workflow element
# TODO: implement check
class SubmissionOnCVFold(db.Model):
    """Submission is an abstract (untrained) submission. SubmissionOnCVFold
    is an instantiation of Submission, to be trained on a data file and a cv
    fold. We don't actually store the trained model in the db (lack of disk and
    pickling issues), so trained submission is not a database column. On the
    other hand, we will store train, valid, and test predictions. In a sense
    substituting CPU time for storage."""

    __tablename__ = 'submission_on_cv_folds'

    id = db.Column(db.Integer, primary_key=True)

    submission_id = db.Column(
        db.Integer, db.ForeignKey('submissions.id'), nullable=False)
    submission = db.relationship(
        'Submission', backref=db.backref(
            'on_cv_folds', cascade="all, delete-orphan"))

    cv_fold_id = db.Column(
        db.Integer, db.ForeignKey('cv_folds.id'), nullable=False)
    cv_fold = db.relationship(
        'CVFold', backref=db.backref(
            'submissions', cascade="all, delete-orphan"))

    # filled by cv_fold.get_combined_predictions
    contributivity = db.Column(db.Float, default=0.0)
    best = db.Column(db.Boolean, default=False)

    # prediction on the full training set, including train and valid points
    # properties train_predictions and valid_predictions will make the slicing
    full_train_predictions = db.Column(PredictionType, default=None)
    test_predictions = db.Column(PredictionType, default=None)
    train_time = db.Column(db.Float, default=0.0)
    valid_time = db.Column(db.Float, default=0.0)
    test_time = db.Column(db.Float, default=0.0)
    train_score = db.Column(ScoreType, default=0.0)
    valid_score = db.Column(ScoreType, default=0.0)
    test_score = db.Column(ScoreType, default=0.0)
    state = db.Column(submission_states, default='new')
    error_msg = db.Column(db.String, default='')

    # later also ramp_id or data_id
    db.UniqueConstraint(submission_id, cv_fold_id, name='sc_constraint')

    def __repr__(self):
        repr = 'state = {}, valid_score = {}, test_score = {}, c = {}'\
            ', best = {}'.format(
                self.state, self.valid_score, self.test_score,
                self.contributivity, self.best)
        return repr

    @hybrid_property
    def is_public_leaderboard(self):
        return (self.state == 'validated') | (self.state == 'tested')

    @hybrid_property
    def is_error(self):
        return (self.state == 'training_error') |\
            (self.state == 'checking_error') |\
            (self.state == 'validating_error') |\
            (self.state == 'testing_error')

    @property
    def train_predictions(self):
        specific = config.config_object.specific
        return specific.Predictions(
            y_pred=self.full_train_predictions.y_pred[self.cv_fold.train_is])

    @property
    def valid_predictions(self):
        specific = config.config_object.specific
        return specific.Predictions(
            y_pred=self.full_train_predictions.y_pred[self.cv_fold.test_is])

    def compute_train_scores(self):
        specific = config.config_object.specific
        true_full_train_predictions = generic.get_true_predictions_train()
        self.train_score = specific.score(
            true_full_train_predictions, self.full_train_predictions,
            self.cv_fold.train_is)
        db.session.commit()

    def compute_valid_scores(self):
        specific = config.config_object.specific
        true_full_train_predictions = generic.get_true_predictions_train()
        self.valid_score = specific.score(
            true_full_train_predictions, self.full_train_predictions,
            self.cv_fold.test_is)
        db.session.commit()

    def compute_test_scores(self):
        specific = config.config_object.specific
        true_test_predictions = generic.get_true_predictions_test()
        self.test_score = specific.score(
            true_test_predictions, self.test_predictions)
        db.session.commit()

    def update(self, detached_submission_on_cv_fold):
        """From trained DetachedSubmissionOnCVFold."""
        self.state = detached_submission_on_cv_fold.state
        if self.is_error:
            self.error_msg = detached_submission_on_cv_fold.error_msg
        else:
            if self.state in ['trained', 'validated', 'tested']:
                self.train_time = detached_submission_on_cv_fold.train_time
            if self.state in ['validated', 'tested']:
                self.valid_time = detached_submission_on_cv_fold.valid_time
                self.full_train_predictions =\
                    detached_submission_on_cv_fold.full_train_predictions
                self.compute_train_scores()
                self.compute_valid_scores()
            if self.state in ['tested']:
                self.test_time = detached_submission_on_cv_fold.test_time
                self.test_predictions =\
                    detached_submission_on_cv_fold.test_predictions
                self.compute_test_scores()
        db.session.commit()


class DetachedSubmissionOnCVFold(object):
    """This class is a copy of SubmissionOnCVFold, all the fields we need in
    train and test. It's because SQLAlchemy objects don't persist through
    multiprocessing jobs. Maybe eliminated if we do the parallelization
    differently, though I doubt it.
    """

    def __init__(self, submission_on_cv_fold):
        self.train_is = submission_on_cv_fold.cv_fold.train_is
        self.test_is = submission_on_cv_fold.cv_fold.test_is
        self.full_train_predictions =\
            submission_on_cv_fold.full_train_predictions
        self.test_predictions = submission_on_cv_fold.test_predictions
        self.full_train_predictions =\
            submission_on_cv_fold.full_train_predictions
        self.test_predictions = submission_on_cv_fold.test_predictions
        self.state = submission_on_cv_fold.state
        self.name = submission_on_cv_fold.submission.team.name + '/'\
            + submission_on_cv_fold.submission.name
        self.module = submission_on_cv_fold.submission.module
        self.error_msg = submission_on_cv_fold.error_msg
        self.train_time = submission_on_cv_fold.train_time
        self.valid_time = submission_on_cv_fold.valid_time
        self.test_time = submission_on_cv_fold.test_time
        self.trained_submission = None

    def __repr__(self):
        repr = 'Submission({}) on fold {}'.format(
            self.name, str(self.train_is)[:10])
        return repr


class UserInteraction(db.Model):
    __tablename__ = 'user_interactions'

    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, nullable=False)
    interaction = db.Column(db.String, nullable=False)
    note = db.Column(db.String, default=None)
    submission_file_diff = db.Column(db.String, default=None)
    submission_file_similarity = db.Column(db.Float, default=None)
    ip = db.Column(db.String, default=None)

    user_id = db.Column(
        db.Integer, db.ForeignKey('users.id'), nullable=False)
    user = db.relationship('User', backref=db.backref('user_interactions'))

    team_id = db.Column(
        db.Integer, db.ForeignKey('teams.id'))
    team = db.relationship('Team', backref=db.backref('user_interactions'))

    submission_id = db.Column(
        db.Integer, db.ForeignKey('submissions.id'))
    submission = db.relationship(
        'Submission', backref=db.backref('user_interactions'))

    submission_file_id = db.Column(
        db.Integer, db.ForeignKey('submission_files.id'))
    submission_file = db.relationship(
        'SubmissionFile', backref=db.backref('user_interactions'))

    def __init__(self, user, interaction, note=None, submission=None,
                 submission_file=None, diff=None, similarity=None):
        self.timestamp = datetime.datetime.utcnow()
        self.interaction = interaction
        self.user = user
        self.team = get_active_user_team(user)
        self.ip = request.environ['REMOTE_ADDR']
        self.note = note
        self.submission = submission
        self.submission_file = submission_file
        self.submission_file_diff = diff
        self.submission_file_similarity = similarity


class NameClashError(Exception):
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)


class MergeTeamError(Exception):
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)


class DuplicateSubmissionError(Exception):
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)


class TooEarlySubmissionError(Exception):
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)


class MissingSubmissionFileError(Exception):
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)


class MissingExtensionError(Exception):
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)
