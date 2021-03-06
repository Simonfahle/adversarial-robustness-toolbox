import logging
import os
from os import listdir, path
import pickle
import tempfile
import warnings

import keras
import numpy as np
import pytest
from tensorflow.keras.callbacks import LearningRateScheduler

from art.defences.preprocessor import FeatureSqueezing, JpegCompression, SpatialSmoothing

logger = logging.getLogger(__name__)


def is_keras_2_3():
    if int(keras.__version__.split(".")[0]) == 2 and int(keras.__version__.split(".")[1]) >= 3:
        return True
    return False


def test_layers(get_default_mnist_subset, framework, is_tf_version_2, image_dl_estimator):
    try:
        classifier, _ = image_dl_estimator(one_classifier=True, from_logits=True)
        if classifier is not None:
            (_, _), (x_test_mnist, y_test_mnist) = get_default_mnist_subset

            if framework == "tensorflow" and is_tf_version_2:
                raise NotImplementedError(
                    "fw_agnostic_backend_test_layers not implemented for framework {0}".format(framework)
                )

            batch_size = 128
            for i, name in enumerate(classifier.layer_names):
                activation_i = classifier.get_activations(x_test_mnist, i, batch_size=batch_size)
                activation_name = classifier.get_activations(x_test_mnist, name, batch_size=batch_size)
                np.testing.assert_array_equal(activation_name, activation_i)
    except NotImplementedError as e:
        warnings.warn(UserWarning(e))


def test_loss_gradient_with_wildcard(image_dl_estimator):
    classifier, _ = image_dl_estimator(one_classifier=True, wildcard=True)
    if classifier is not None:
        shapes = [(1, 10, 1), (1, 20, 1)]
        for shape in shapes:
            x = np.random.normal(size=shape)
            loss_gradient = classifier.loss_gradient(x, y=[1])
            assert loss_gradient.shape == shape

            class_gradient = classifier.class_gradient(x, 0)
            assert class_gradient[0].shape == shape


# Note: because mxnet only supports 1 concurrent version of a model if we fit that model, all expected values will
# change for all other tests using that fitted model
@pytest.mark.skipMlFramework("mxnet")
def test_fit(get_default_mnist_subset, default_batch_size, image_dl_estimator):
    try:
        (x_train_mnist, y_train_mnist), (x_test_mnist, y_test_mnist) = get_default_mnist_subset

        labels = np.argmax(y_test_mnist, axis=1)
        classifier, sess = image_dl_estimator(one_classifier=True, from_logits=True)
        if classifier is not None:
            accuracy = np.sum(np.argmax(classifier.predict(x_test_mnist), axis=1) == labels) / x_test_mnist.shape[0]
            np.testing.assert_array_almost_equal(accuracy, 0.32, decimal=2)

            classifier.fit(x_train_mnist, y_train_mnist, batch_size=default_batch_size, nb_epochs=2)
            accuracy_2 = np.sum(np.argmax(classifier.predict(x_test_mnist), axis=1) == labels) / x_test_mnist.shape[0]
            assert accuracy_2 == pytest.approx(0.73, abs=0.06)
    except NotImplementedError as e:
        warnings.warn(UserWarning(e))


def test_predict(
    request, framework, get_default_mnist_subset, image_dl_estimator, expected_values, store_expected_values
):
    if framework == "keras" and is_keras_2_3() is False:
        # Keras 2.2 does not support creating classifiers with logits=True so skipping this test
        return

    (_, _), (x_test_mnist, y_test_mnist) = get_default_mnist_subset

    classifier, _ = image_dl_estimator(one_classifier=True, from_logits=True)

    if classifier is not None:
        y_predicted = classifier.predict(x_test_mnist[0:1])
        np.testing.assert_array_almost_equal(y_predicted, expected_values(), decimal=4)


def test_shapes(get_default_mnist_subset, image_dl_estimator):
    try:
        (_, _), (x_test_mnist, y_test_mnist) = get_default_mnist_subset
        classifier, sess = image_dl_estimator(one_classifier=True, from_logits=True)

        if classifier is not None:
            predictions = classifier.predict(x_test_mnist)
            assert predictions.shape == y_test_mnist.shape

            assert classifier.nb_classes == 10

            class_gradients = classifier.class_gradient(x_test_mnist[:11])
            assert class_gradients.shape == tuple([11, 10] + list(x_test_mnist[1].shape))

            loss_gradients = classifier.loss_gradient(x_test_mnist[:11], y_test_mnist[:11])
            assert loss_gradients.shape == x_test_mnist[:11].shape

    except NotImplementedError as e:
        warnings.warn(UserWarning(e))


# TODO skipping with kerastf because overall tests are taking too long to run - unskip once tests run under limit time
@pytest.mark.skipMlFramework("kerastf")
@pytest.mark.parametrize("from_logits", [True, False])
@pytest.mark.parametrize(
    "loss_name",
    ["categorical_crossentropy", "categorical_hinge", "sparse_categorical_crossentropy", "kullback_leibler_divergence"],
)
def test_loss_functions(
    image_dl_estimator,
    get_default_mnist_subset,
    loss_name,
    supported_losses_proba,
    supported_losses_logit,
    store_expected_values,
    supported_losses_types,
    from_logits,
    expected_values,
):
    # prediction and class_gradient should be independent of logits/probabilities and of loss function

    try:
        (_, _), (x_test_mnist, y_test_mnist) = get_default_mnist_subset

        if from_logits:
            supported_losses = supported_losses_logit()
        else:
            supported_losses = supported_losses_proba()

        for loss_type in supported_losses_types():
            (y_test_pred_exp, class_gradient_exp, loss_grad_exp) = expected_values()
            # store_expected_values(expected_values)

            if loss_name + "_" + loss_type in supported_losses:
                classifier, _ = image_dl_estimator(
                    one_classifier=True, loss_name=loss_name, loss_type=loss_type, from_logits=from_logits
                )

                y_test_pred_exp = np.argmax(classifier.predict(x=x_test_mnist), axis=1)
                np.testing.assert_array_equal(y_test_pred_exp, y_test_pred_exp)

                class_gradient = classifier.class_gradient(x_test_mnist, label=5)
                # np.testing.assert_array_almost_equal(class_gradient[99, 0, 14, :, 0], class_gradient_prob_exp)
                np.testing.assert_array_almost_equal(class_gradient[99, 0, 14, :, 0], class_gradient_exp)

                loss_gradient_value = classifier.loss_gradient(x=x_test_mnist, y=y_test_mnist)
                np.testing.assert_array_almost_equal(loss_gradient_value[99, 14, :, 0], loss_grad_exp[loss_name])

    except NotImplementedError as e:
        warnings.warn(UserWarning(e))


def test_pickle(image_dl_estimator, image_dl_estimator_defended, tmp_path):
    full_path = os.path.join(tmp_path, "my_classifier.p")

    classifier, _ = image_dl_estimator(one_classifier=True, functional=True)
    if classifier is not None:
        with open(full_path, "wb") as save_file:
            pickle.dump(classifier, save_file)

        with open(full_path, "rb") as load_file:
            loaded = pickle.load(load_file)

        assert (classifier._clip_values == loaded._clip_values).all()
        assert classifier._channel_index == loaded._channel_index
        assert classifier._use_logits == loaded._use_logits
        assert classifier._input_layer == loaded._input_layer


def test_functional_model(image_dl_estimator):
    # Need to update the functional_model code to produce a model with more than one input and output layers...
    classifier, _ = image_dl_estimator(one_classifier=True, functional=True, input_layer=1, output_layer=1)
    if classifier is not None:
        assert "input1" in classifier._input.name
        assert "output1" in classifier._output.name

    classifier, _ = image_dl_estimator(one_classifier=True, functional=True, input_layer=0, output_layer=0)
    if classifier is not None:
        assert "input0" in classifier._input.name
        assert "output0" in classifier._output.name


@pytest.mark.skipMlFramework("mxnet", "tensorflow", "pytorch")
def test_fit_kwargs(image_dl_estimator, get_default_mnist_subset, default_batch_size):
    try:
        (x_train_mnist, y_train_mnist), (_, _) = get_default_mnist_subset

        def get_lr(_):
            return 0.01

        # Test a valid callback
        classifier, _ = image_dl_estimator(one_classifier=True, from_logits=True)
        if classifier is not None:
            kwargs = {"callbacks": [LearningRateScheduler(get_lr)]}
            classifier.fit(x_train_mnist, y_train_mnist, batch_size=default_batch_size, nb_epochs=1, **kwargs)

            # Test failure for invalid parameters
            kwargs = {"epochs": 1}
            with pytest.raises(TypeError) as exception:
                classifier.fit(x_train_mnist, y_train_mnist, batch_size=default_batch_size, nb_epochs=1, **kwargs)

            assert "multiple values for keyword argument" in str(exception)

    except NotImplementedError as e:
        warnings.warn(UserWarning(e))


def test_defences_predict(get_default_mnist_subset, image_dl_estimator_defended, image_dl_estimator):
    (_, _), (x_test_mnist, y_test_mnist) = get_default_mnist_subset

    classifier, _ = image_dl_estimator_defended(
        one_classifier=True, defenses=["FeatureSqueezing", "JpegCompression", "SpatialSmoothing"]
    )
    if classifier is not None:
        assert len(classifier.preprocessing_defences) == 3

        predictions_classifier = classifier.predict(x_test_mnist)

        # Apply the same defences by hand
        x_test_defense = x_test_mnist
        clip_values = (0, 1)
        fs = FeatureSqueezing(clip_values=clip_values, bit_depth=2)
        x_test_defense, _ = fs(x_test_defense, y_test_mnist)
        jpeg = JpegCompression(clip_values=clip_values, apply_predict=True)
        x_test_defense, _ = jpeg(x_test_defense, y_test_mnist)
        smooth = SpatialSmoothing()
        x_test_defense, _ = smooth(x_test_defense, y_test_mnist)
        # classifier, _ = get_image_classifier_list(one_classifier=True, from_logits=True)
        classifier, _ = image_dl_estimator(one_classifier=True)
        predictions_check = classifier._model.predict(x_test_defense)

        # Check that the prediction results match
        np.testing.assert_array_almost_equal(predictions_classifier, predictions_check, decimal=4)


# Note: because mxnet only supports 1 concurrent version of a model if we fit that model, all expected values will
# change for all other tests using that fitted model
@pytest.mark.skipMlFramework("mxnet")
def test_fit_image_generator(
    framework, is_tf_version_2, image_dl_estimator, image_data_generator, get_default_mnist_subset
):
    try:
        if framework == "tensorflow" and is_tf_version_2:
            return

        classifier, sess = image_dl_estimator(one_classifier=True, from_logits=True)
        if classifier is not None:
            (_, _), (x_test_mnist, y_test_mnist) = get_default_mnist_subset

            true_class = np.argmax(y_test_mnist, axis=1)

            predictions = classifier.predict(x_test_mnist)
            prediction_class = np.argmax(predictions, axis=1)
            pre_fit_accuracy = np.sum(prediction_class == true_class) / x_test_mnist.shape[0]

            assert pre_fit_accuracy == pytest.approx(0.32, abs=0.01)

            data_gen = image_data_generator(sess=sess)
            classifier.fit_generator(generator=data_gen, nb_epochs=2)
            predictions = classifier.predict(x_test_mnist)
            prediction_class = np.argmax(predictions, axis=1)
            post_fit_accuracy = np.sum(prediction_class == true_class) / x_test_mnist.shape[0]

            assert post_fit_accuracy == pytest.approx(0.75, abs=0.08)

    except NotImplementedError as e:
        warnings.warn(UserWarning(e))


def test_loss_gradient(
    framework,
    is_tf_version_2,
    get_default_mnist_subset,
    image_dl_estimator,
    expected_values,
    mnist_shape,
    store_expected_values,
):
    if framework == "keras" and is_keras_2_3() is False:
        # Keras 2.2 does not support creating classifiers with logits=True so skipping this test d
        return

    (expected_gradients_1, expected_gradients_2) = expected_values()

    (_, _), (x_test_mnist, y_test_mnist) = get_default_mnist_subset
    classifier, _ = image_dl_estimator(one_classifier=True, from_logits=True)

    if classifier is not None:
        gradients = classifier.loss_gradient(x_test_mnist, y_test_mnist)

        assert gradients.shape == (x_test_mnist.shape[0],) + mnist_shape

        if mnist_shape[0] == 1:
            sub_gradients = gradients[0, 0, :, 14]
        else:
            sub_gradients = gradients[0, :, 14, 0]

        np.testing.assert_array_almost_equal(
            sub_gradients, expected_gradients_1[0], decimal=expected_gradients_1[1],
        )

        if mnist_shape[0] == 1:
            sub_gradients = gradients[0, 0, 14, :]
        else:
            sub_gradients = gradients[0, 14, :, 0]

        np.testing.assert_array_almost_equal(
            sub_gradients, expected_gradients_2[0], decimal=expected_gradients_2[1],
        )


def test_nb_classes(image_dl_estimator):
    try:
        classifier, _ = image_dl_estimator(one_classifier=True, from_logits=True)
        if classifier is not None:
            assert classifier.nb_classes == 10
    except NotImplementedError as e:
        warnings.warn(UserWarning(e))


def test_input_shape(image_dl_estimator, mnist_shape):
    try:
        classifier, _ = image_dl_estimator(one_classifier=True, from_logits=True)
        if classifier is not None:
            assert classifier.input_shape == mnist_shape
    except NotImplementedError as e:
        warnings.warn(UserWarning(e))


def test_save(image_dl_estimator):
    try:
        classifier, _ = image_dl_estimator(one_classifier=True, from_logits=True)
        if classifier is not None:
            t_file = tempfile.NamedTemporaryFile()
            model_path = t_file.name
            t_file.close()
            filename = "model_to_save"
            classifier.save(filename, path=model_path)

            assert path.exists(model_path)

            created_model = False

            for file in listdir(model_path):
                if filename in file:
                    created_model = True
            assert created_model

    except NotImplementedError as e:
        warnings.warn(UserWarning(e))


def test_repr(image_dl_estimator, framework, expected_values, store_expected_values):
    try:
        classifier, _ = image_dl_estimator(one_classifier=True, from_logits=True)
        if classifier is not None:

            repr_ = repr(classifier)
            for message in expected_values():
                assert message in repr_, "{0}: was not contained within repr".format(message)

    except NotImplementedError as e:
        warnings.warn(UserWarning(e))


def test_save(image_dl_estimator, get_default_mnist_subset, tmp_path):
    try:
        classifier, _ = image_dl_estimator(one_classifier=True)
        if classifier is not None:
            (x_train_mnist, y_train_mnist), (_, _) = get_default_mnist_subset
            classifier.fit(x_train_mnist, y_train_mnist, batch_size=128, nb_epochs=2)
            full_path = tmp_path / "sub"
            full_path.mkdir()

            assert not os.listdir(full_path._str)
            classifier.save("modelFile", path=full_path._str)
            assert os.listdir(full_path._str)
    except NotImplementedError as e:
        warnings.warn(UserWarning(e))


@pytest.mark.skipMlFramework("mxnet")
def test_class_gradient(
    framework, image_dl_estimator, get_default_mnist_subset, mnist_shape, store_expected_values, expected_values
):
    if framework == "keras" and is_keras_2_3() is False:
        # Keras 2.2 does not support creating classifiers with logits=True so skipping this test
        return

    (_, _), (x_test_mnist, y_test_mnist) = get_default_mnist_subset

    classifier, _ = image_dl_estimator(one_classifier=True, from_logits=True)
    if classifier is not None:

        (
            grad_1_all_labels,
            grad_2_all_labels,
            grad_1_label5,
            grad_2_label5,
            grad_1_labelArray,
            grad_2_labelArray,
            labels_list,
        ) = expected_values()

        labels = np.array(labels_list, dtype=object)

        # TODO we should consider checking channel independent columns to make this test truly framework independent
        def get_gradient1_column(gradients):
            if mnist_shape[0] == 1:
                return gradients[0, 5, 0, 14, :]  # expected_gradients_1_all_labels
            else:
                return gradients[0, 5, 14, :, 0]

        def get_gradient2_column(gradients):
            if mnist_shape[0] == 1:
                return gradients[0, 5, 0, :, 14]  # expected_gradients_2_all_labels
            else:
                return gradients[0, 5, :, 14, 0]

        def get_gradient3_column(gradients):
            if mnist_shape[0] == 1:
                return gradients[0, 0, 0, 14, :]  # expected_gradients_1_label5
            else:
                return gradients[0, 0, 14, :, 0]

        def get_gradient4_column(gradients):
            if mnist_shape[0] == 1:
                return gradients[0, 0, 0, :, 14]  # expected_gradients_2_all_labels
            else:
                return gradients[0, 0, :, 14, 0]

        # Test all gradients label
        gradients = classifier.class_gradient(x_test_mnist)

        new_shape = (x_test_mnist.shape[0], 10,) + mnist_shape
        assert gradients.shape == new_shape

        sub_gradients2 = get_gradient2_column(gradients)
        np.testing.assert_array_almost_equal(
            sub_gradients2, grad_2_all_labels[0], decimal=4,
        )

        # Test 1 gradient label = 5
        gradients = classifier.class_gradient(x_test_mnist, label=5)

        assert gradients.shape == (x_test_mnist.shape[0], 1,) + mnist_shape

        sub_gradients2 = get_gradient3_column(gradients)
        np.testing.assert_array_almost_equal(
            sub_gradients2, grad_1_label5[0], decimal=4,
        )

        sub_gradients4 = get_gradient4_column(gradients)
        np.testing.assert_array_almost_equal(
            sub_gradients4, grad_2_label5[0], decimal=4,
        )

        # # Test a set of gradients label = array
        gradients = classifier.class_gradient(x_test_mnist, label=labels)

        new_shape = (x_test_mnist.shape[0], 1,) + mnist_shape
        assert gradients.shape == new_shape

        sub_gradients5 = get_gradient3_column(gradients)
        np.testing.assert_array_almost_equal(
            sub_gradients5, grad_1_labelArray[0], decimal=4,
        )

        sub_gradients6 = get_gradient4_column(gradients)
        np.testing.assert_array_almost_equal(
            sub_gradients6, grad_2_labelArray[0], decimal=4,
        )


def test_learning_phase(image_dl_estimator):
    try:
        classifier, _ = image_dl_estimator(one_classifier=True)
        if classifier is not None:
            classifier.set_learning_phase(False)
            assert classifier.learning_phase is False
            classifier.set_learning_phase(True)
            assert classifier.learning_phase
            assert hasattr(classifier, "_learning_phase")
    except NotImplementedError as e:
        warnings.warn(UserWarning(e))
