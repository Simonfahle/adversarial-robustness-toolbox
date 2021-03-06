# MIT License
#
# Copyright (C) The Adversarial Robustness Toolbox (ART) Authors 2020
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
# documentation files (the "Software"), to deal in the Software without restriction, including without limitation the
# rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit
# persons to whom the Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all copies or substantial portions of the
# Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
# WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
# TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
import logging
import pytest

import numpy as np

from art.attacks.evasion import ShadowAttack
from art.estimators.estimator import BaseEstimator, LossGradientsMixin
from art.estimators.classification.classifier import ClassifierMixin

from tests.attacks.utils import backend_test_classifier_type_check_fail

logger = logging.getLogger(__name__)


@pytest.fixture()
def fix_get_mnist_subset(get_mnist_dataset):
    (x_train_mnist, y_train_mnist), (x_test_mnist, y_test_mnist) = get_mnist_dataset
    n_train = 100
    n_test = 11
    yield x_train_mnist[:n_train], y_train_mnist[:n_train], x_test_mnist[:n_test], y_test_mnist[:n_test]


@pytest.mark.only_with_platform("pytorch")
def test_generate(fix_get_mnist_subset, image_dl_estimator_for_attack):
    classifier_list = image_dl_estimator_for_attack(ShadowAttack)

    for classifier in classifier_list:
        attack = ShadowAttack(
            estimator=classifier,
            sigma=0.5,
            nb_steps=3,
            learning_rate=0.1,
            lambda_tv=0.3,
            lambda_c=1.0,
            lambda_s=0.5,
            batch_size=32,
            targeted=True,
        )

        (x_train_mnist, y_train_mnist, x_test_mnist, y_test_mnist) = fix_get_mnist_subset

        x_train_mnist_adv = attack.generate(x=x_train_mnist[0:1], y=y_train_mnist[0:1])

        assert np.max(np.abs(x_train_mnist_adv - x_train_mnist[0:1])) == pytest.approx(0.34966960549354553, abs=0.06)


@pytest.mark.only_with_platform("pytorch")
def test_get_regularisation_loss_gradients(fix_get_mnist_subset, image_dl_estimator_for_attack):
    classifier_list = image_dl_estimator_for_attack(ShadowAttack)

    for classifier in classifier_list:

        attack = ShadowAttack(
            estimator=classifier,
            sigma=0.5,
            nb_steps=3,
            learning_rate=0.1,
            lambda_tv=0.3,
            lambda_c=1.0,
            lambda_s=0.5,
            batch_size=32,
            targeted=True,
        )

        (x_train_mnist, _, _, _) = fix_get_mnist_subset

        gradients = attack._get_regularisation_loss_gradients(x_train_mnist[0:1])

        gradients_expected = np.array(
            [
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                -0.27294118,
                -0.36906054,
                0.83799828,
                0.40741005,
                0.65682181,
                -0.13141348,
                -0.39729583,
                -0.12235294,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
            ]
        )

        if attack.framework == "pytorch":
            np.testing.assert_array_almost_equal(gradients[0, 0, 14, :], gradients_expected, decimal=3)
        else:
            np.testing.assert_array_almost_equal(gradients[0, 14, :, 0], gradients_expected, decimal=3)


def test_classifier_type_check_fail():
    backend_test_classifier_type_check_fail(ShadowAttack, [BaseEstimator, LossGradientsMixin, ClassifierMixin])


if __name__ == "__main__":
    pytest.cmdline.main("-q -s {} --mlFramework=pytorch --durations=0".format(__file__).split(" "))
