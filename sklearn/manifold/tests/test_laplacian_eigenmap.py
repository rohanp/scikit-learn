from nose.tools import assert_true
from nose.tools import assert_equal

from scipy.sparse import csr_matrix
from scipy.sparse import csc_matrix
from scipy.linalg import eigh
import numpy as np
from numpy.testing import assert_array_almost_equal

from nose.tools import assert_raises
from nose.plugins.skip import SkipTest

from sklearn.manifold.laplacian_eigenmap_ import laplacian_eigenmap, LaplacianEigenmap
from sklearn.manifold.laplacian_eigenmap_ import _graph_is_connected
from sklearn.manifold.laplacian_eigenmap_ import _graph_connected_component
from sklearn.manifold import laplacian_eigenmap
from sklearn.metrics.pairwise import rbf_kernel
from sklearn.metrics import normalized_mutual_info_score
from sklearn.cluster import KMeans
from sklearn.datasets.samples_generator import make_blobs
from sklearn.utils.graph import graph_laplacian
from sklearn.utils.extmath import _deterministic_vector_sign_flip


# non centered, sparembedding centers to check the
centers = np.array([
    [0.0, 5.0, 0.0, 0.0, 0.0],
    [0.0, 0.0, 4.0, 0.0, 0.0],
    [1.0, 0.0, 0.0, 5.0, 1.0],
])
n_samples = 1000
n_clusters, n_features = centers.shape
S, true_labels = make_blobs(n_samples=n_samples, centers=centers,
                            cluster_std=1., random_state=42)


def _check_with_col_sign_flipping(A, B, tol=0.0):
    """ Check array A and B are equal with possible sign flipping on
    each columns"""
    sign = True
    for column_idx in range(A.shape[1]):
        sign = sign and ((((A[:, column_idx] -
                            B[:, column_idx]) ** 2).mean() <= tol ** 2) or
                         (((A[:, column_idx] +
                            B[:, column_idx]) ** 2).mean() <= tol ** 2))
        if not sign:
            return False
    return True


def test_laplacian_eigenmap_two_components(seed=36):
    # Test laplacian eigenmap with two components
    random_state = np.random.RandomState(seed)
    n_sample = 100
    affinity = np.zeros(shape=[n_sample * 2,
                               n_sample * 2])
    # first component
    affinity[0:n_sample,
             0:n_sample] = np.abs(random_state.randn(n_sample, n_sample)) + 2
    # second component
    affinity[n_sample::,
             n_sample::] = np.abs(random_state.randn(n_sample, n_sample)) + 2

    # Test of internal _graph_connected_component before connection
    component = _graph_connected_component(affinity, 0)
    assert_true(component[:n_sample].all())
    assert_true(not component[n_sample:].any())
    component = _graph_connected_component(affinity, -1)
    assert_true(not component[:n_sample].any())
    assert_true(component[n_sample:].all())

    # connection
    affinity[0, n_sample + 1] = 1
    affinity[n_sample + 1, 0] = 1
    affinity.flat[::2 * n_sample + 1] = 0
    affinity = 0.5 * (affinity + affinity.T)

    true_label = np.zeros(shape=2 * n_sample)
    true_label[0:n_sample] = 1

    embedding_precomp = LaplacianEigenmap(n_components=1, affinity="precomputed",
                                   random_state=np.random.RandomState(seed))
    embedded_coordinate = embedding_precomp.fit_transform(affinity)
    # Some numpy versions are touchy with types
    embedded_coordinate = \
        embedding_precomp.fit_transform(affinity.astype(np.float32))
    # thresholding on the first components using 0.
    label_ = np.array(embedded_coordinate.ravel() < 0, dtype="float")
    assert_equal(normalized_mutual_info_score(true_label, label_), 1.0)


def test_laplacian_eigenmap_precomputed_affinity(seed=36):
    # Test laplacian eigenmap with precomputed kernel
    gamma = 1.0
    embedding_precomp = LaplacianEigenmap(n_components=2, affinity="precomputed",
                                   random_state=np.random.RandomState(seed))
    embedding_rbf = LaplacianEigenmap(n_components=2, affinity="rbf",
                               gamma=gamma,
                               random_state=np.random.RandomState(seed))
    embed_precomp = embedding_precomp.fit_transform(rbf_kernel(S, gamma=gamma))
    embed_rbf = embedding_rbf.fit_transform(S)
    assert_array_almost_equal(
        embedding_precomp.affinity_matrix_, embedding_rbf.affinity_matrix_)
    assert_true(_check_with_col_sign_flipping(embed_precomp, embed_rbf, 0.05))


def test_laplacian_eigenmap_callable_affinity(seed=36):
    # Test laplacian eigenmap with callable affinity
    gamma = 0.9
    kern = rbf_kernel(S, gamma=gamma)
    embedding_callable = LaplacianEigenmap(n_components=2,
                                    affinity=(
                                        lambda x: rbf_kernel(x, gamma=gamma)),
                                    gamma=gamma,
                                    random_state=np.random.RandomState(seed))
    embedding_rbf = LaplacianEigenmap(n_components=2, affinity="rbf",
                               gamma=gamma,
                               random_state=np.random.RandomState(seed))
    embed_rbf = embedding_rbf.fit_transform(S)
    embed_callable = embedding_callable.fit_transform(S)
    assert_array_almost_equal(
        embedding_callable.affinity_matrix_, embedding_rbf.affinity_matrix_)
    assert_array_almost_equal(kern, embedding_rbf.affinity_matrix_)
    assert_true(
        _check_with_col_sign_flipping(embed_rbf, embed_callable, 0.05))


def test_laplacian_eigenmap_amg_solver(seed=36):
    # Test laplacian eigenmap with amg solver
    try:
        from pyamg import smoothed_aggregation_solver
    except ImportError:
        raise SkipTest("pyamg not available.")

    embedding_amg = LaplacianEigenmap(n_components=2, affinity="nearest_neighbors",
                               eigen_solver="amg", n_neighbors=5,
                               random_state=np.random.RandomState(seed))
    embedding_arpack = LaplacianEigenmap(n_components=2, affinity="nearest_neighbors",
                                  eigen_solver="arpack", n_neighbors=5,
                                  random_state=np.random.RandomState(seed))
    embed_amg = embedding_amg.fit_transform(S)
    embed_arpack = embedding_arpack.fit_transform(S)
    assert_true(_check_with_col_sign_flipping(embed_amg, embed_arpack, 0.05))


def test_pipeline_spectral_clustering(seed=36):
    # Test using pipeline to do spectral clustering
    random_state = np.random.RandomState(seed)
    embedding_rbf = LaplacianEigenmap(n_components=n_clusters,
                               affinity="rbf",
                               random_state=random_state)
    embedding_knn = LaplacianEigenmap(n_components=n_clusters,
                               affinity="nearest_neighbors",
                               n_neighbors=5,
                               random_state=random_state)
    for embedding in [embedding_rbf, embedding_knn]:
        km = KMeans(n_clusters=n_clusters, random_state=random_state)
        km.fit(embedding.fit_transform(S))
        assert_array_almost_equal(
            normalized_mutual_info_score(
                km.labels_,
                true_labels), 1.0, 2)


def test_laplacian_eigenmap_unknown_eigensolver(seed=36):
    # Test that SpectralClustering fails with an unknown eigensolver
    embedding = LaplacianEigenmap(n_components=1, affinity="precomputed",
                           random_state=np.random.RandomState(seed),
                           eigen_solver="<unknown>")
    assert_raises(ValueError, embedding.fit, S)


def test_laplacian_eigenmap_unknown_affinity(seed=36):
    # Test that SpectralClustering fails with an unknown affinity type
    embedding = LaplacianEigenmap(n_components=1, affinity="<unknown>",
                           random_state=np.random.RandomState(seed))
    assert_raises(ValueError, embedding.fit, S)


def test_connectivity(seed=36):
    # Test that graph connectivity test works as expected
    graph = np.array([[1, 0, 0, 0, 0],
                      [0, 1, 1, 0, 0],
                      [0, 1, 1, 1, 0],
                      [0, 0, 1, 1, 1],
                      [0, 0, 0, 1, 1]])
    assert_equal(_graph_is_connected(graph), False)
    assert_equal(_graph_is_connected(csr_matrix(graph)), False)
    assert_equal(_graph_is_connected(csc_matrix(graph)), False)
    graph = np.array([[1, 1, 0, 0, 0],
                      [1, 1, 1, 0, 0],
                      [0, 1, 1, 1, 0],
                      [0, 0, 1, 1, 1],
                      [0, 0, 0, 1, 1]])
    assert_equal(_graph_is_connected(graph), True)
    assert_equal(_graph_is_connected(csr_matrix(graph)), True)
    assert_equal(_graph_is_connected(csc_matrix(graph)), True)


def test_laplacian_eigenmap_deterministic():
    # Test that laplacian eigenmap is deterministic
    random_state = np.random.RandomState(36)
    data = random_state.randn(10, 30)
    sims = rbf_kernel(data)
    embedding_1 = laplacian_eigenmap(sims)
    embedding_2 = laplacian_eigenmap(sims)
    assert_array_almost_equal(embedding_1, embedding_2)


def test_laplacian_eigenmap_unnormalized():
    # Test that laplacian_eigenmap is also processing unnormalized laplacian correctly
    random_state = np.random.RandomState(36)
    data = random_state.randn(10, 30)
    sims = rbf_kernel(data)
    n_components = 8
    embedding_1 = laplacian_eigenmap(sims,
                                     norm_laplacian=False,
                                     n_components=n_components,
                                     drop_first=False)

    # Verify using manual computation with denembedding eigh
    laplacian, dd = graph_laplacian(sims, normed=False, return_diag=True)
    _, diffusion_map = eigh(laplacian)
    embedding_2 = diffusion_map.T[:n_components] * dd
    embedding_2 = _deterministic_vector_sign_flip(embedding_2).T

    assert_array_almost_equal(embedding_1, embedding_2)