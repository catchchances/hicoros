#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <cmath>
#include <stdexcept>

namespace {

constexpr double kA = 6378137.0;
constexpr double kF = 1.0 / 298.257223563;
constexpr double kB = 6356752.314245;
constexpr double kGcjA = 6378245.0;
constexpr double kGcjEe = 0.00669342162296594323;
constexpr int kMaxIterations = 200;
constexpr double kConvergenceThreshold = 1e-12;
constexpr double kPi = 3.14159265358979323846;

double radians(double degree) {
    return degree * (kPi / 180.0);
}

double vincenty_distance_m(double lat1, double lon1, double lat2, double lon2) {
    if (lat1 == lat2 && lon1 == lon2) {
        return 0.0;
    }

    const double U1 = std::atan((1.0 - kF) * std::tan(radians(lat1)));
    const double U2 = std::atan((1.0 - kF) * std::tan(radians(lat2)));
    const double L = radians(lon2 - lon1);

    const double sinU1 = std::sin(U1);
    const double cosU1 = std::cos(U1);
    const double sinU2 = std::sin(U2);
    const double cosU2 = std::cos(U2);

    double lambda = L;
    double sinSigma = 0.0;
    double cosSigma = 0.0;
    double sigma = 0.0;
    double sinAlpha = 0.0;
    double cosSqAlpha = 0.0;
    double cos2SigmaM = 0.0;

    for (int i = 0; i < kMaxIterations; ++i) {
        const double sinLambda = std::sin(lambda);
        const double cosLambda = std::cos(lambda);

        sinSigma = std::sqrt(
            std::pow(cosU2 * sinLambda, 2.0) +
            std::pow(cosU1 * sinU2 - sinU1 * cosU2 * cosLambda, 2.0));

        if (sinSigma == 0.0) {
            return 0.0;
        }

        cosSigma = sinU1 * sinU2 + cosU1 * cosU2 * cosLambda;
        sigma = std::atan2(sinSigma, cosSigma);
        sinAlpha = cosU1 * cosU2 * sinLambda / sinSigma;
        cosSqAlpha = 1.0 - sinAlpha * sinAlpha;

        if (cosSqAlpha != 0.0) {
            cos2SigmaM = cosSigma - 2.0 * sinU1 * sinU2 / cosSqAlpha;
        } else {
            cos2SigmaM = 0.0;
        }

        const double C = kF / 16.0 * cosSqAlpha * (4.0 + kF * (4.0 - 3.0 * cosSqAlpha));
        const double prevLambda = lambda;
        lambda = L + (1.0 - C) * kF * sinAlpha *
            (sigma + C * sinSigma *
            (cos2SigmaM + C * cosSigma * (-1.0 + 2.0 * std::pow(cos2SigmaM, 2.0))));

        if (std::fabs(lambda - prevLambda) < kConvergenceThreshold) {
            const double uSq = cosSqAlpha * (kA * kA - kB * kB) / (kB * kB);
            const double A = 1.0 + uSq / 16384.0 * (4096.0 + uSq * (-768.0 + uSq * (320.0 - 175.0 * uSq)));
            const double B = uSq / 1024.0 * (256.0 + uSq * (-128.0 + uSq * (74.0 - 47.0 * uSq)));
            const double deltaSigma =
                B * sinSigma *
                (cos2SigmaM +
                 B / 4.0 *
                     (cosSigma * (-1.0 + 2.0 * std::pow(cos2SigmaM, 2.0)) -
                      B / 6.0 * cos2SigmaM * (-3.0 + 4.0 * std::pow(sinSigma, 2.0)) *
                          (-3.0 + 4.0 * std::pow(cos2SigmaM, 2.0))));

            const double s = kB * A * (sigma - deltaSigma);
            return std::round(s * 1e6) / 1e6;
        }
    }

    throw std::runtime_error("Failed to calculate distance");
}

double transform_lat(double x, double y) {
    double ret =
        -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * std::sqrt(std::fabs(x));
    ret += (20.0 * std::sin(6.0 * x * kPi) + 20.0 * std::sin(2.0 * x * kPi)) * 2.0 / 3.0;
    ret += (20.0 * std::sin(y * kPi) + 40.0 * std::sin(y / 3.0 * kPi)) * 2.0 / 3.0;
    ret += (160.0 * std::sin(y / 12.0 * kPi) + 320.0 * std::sin(y * kPi / 30.0)) * 2.0 / 3.0;
    return ret;
}

double transform_lon(double x, double y) {
    double ret =
        300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * std::sqrt(std::fabs(x));
    ret += (20.0 * std::sin(6.0 * x * kPi) + 20.0 * std::sin(2.0 * x * kPi)) * 2.0 / 3.0;
    ret += (20.0 * std::sin(x * kPi) + 40.0 * std::sin(x / 3.0 * kPi)) * 2.0 / 3.0;
    ret += (150.0 * std::sin(x / 12.0 * kPi) + 300.0 * std::sin(x / 30.0 * kPi)) * 2.0 / 3.0;
    return ret;
}

bool out_of_china(double lat, double lon) {
    return lon < 72.004 || lon > 137.8347 || lat < 0.8293 || lat > 55.8271;
}

void delta_gcj(double lat, double lon, double* d_lat, double* d_lon) {
    const double t_lat = transform_lat(lon - 105.0, lat - 35.0);
    const double t_lon = transform_lon(lon - 105.0, lat - 35.0);
    const double rad_lat = lat / 180.0 * kPi;
    double magic = std::sin(rad_lat);
    magic = 1.0 - kGcjEe * magic * magic;
    const double sqrt_magic = std::sqrt(magic);
    *d_lat = (t_lat * 180.0) / ((kGcjA * (1.0 - kGcjEe)) / (magic * sqrt_magic) * kPi);
    *d_lon = (t_lon * 180.0) / (kGcjA / sqrt_magic * std::cos(rad_lat) * kPi);
}

std::pair<double, double> gcj02_to_wgs84_caijun(double lat, double lon, int max_iter = 10, double eps = 1e-12) {
    if (out_of_china(lat, lon)) {
        return {lat, lon};
    }

    double d_lat = 0.0;
    double d_lon = 0.0;
    delta_gcj(lat, lon, &d_lat, &d_lon);

    double wgs_lat = lat - d_lat;
    double wgs_lon = lon - d_lon;

    for (int i = 0; i < max_iter; ++i) {
        if (out_of_china(wgs_lat, wgs_lon)) {
            break;
        }

        double d2_lat = 0.0;
        double d2_lon = 0.0;
        delta_gcj(wgs_lat, wgs_lon, &d2_lat, &d2_lon);
        const double gcj_lat = wgs_lat + d2_lat;
        const double gcj_lon = wgs_lon + d2_lon;

        const double diff_lat = gcj_lat - lat;
        const double diff_lon = gcj_lon - lon;

        wgs_lat -= diff_lat;
        wgs_lon -= diff_lon;

        if (std::fabs(diff_lat) <= eps && std::fabs(diff_lon) <= eps) {
            break;
        }
    }

    return {wgs_lat, wgs_lon};
}

PyObject* py_vincenty_distance_m(PyObject* /*self*/, PyObject* args) {
    double lat1 = 0.0;
    double lon1 = 0.0;
    double lat2 = 0.0;
    double lon2 = 0.0;

    if (!PyArg_ParseTuple(args, "dddd", &lat1, &lon1, &lat2, &lon2)) {
        return nullptr;
    }

    try {
        return PyFloat_FromDouble(vincenty_distance_m(lat1, lon1, lat2, lon2));
    } catch (const std::exception& ex) {
        PyErr_SetString(PyExc_RuntimeError, ex.what());
        return nullptr;
    }
}

PyObject* py_vincenty_distance_batch_m(PyObject* /*self*/, PyObject* args) {
    PyObject* pair_list_obj = nullptr;
    if (!PyArg_ParseTuple(args, "O", &pair_list_obj)) {
        return nullptr;
    }

    PyObject* pair_seq = PySequence_Fast(pair_list_obj, "Expected a sequence of (lat1, lon1, lat2, lon2)");
    if (!pair_seq) {
        return nullptr;
    }

    const Py_ssize_t n = PySequence_Fast_GET_SIZE(pair_seq);
    PyObject* result = PyList_New(n);
    if (!result) {
        Py_DECREF(pair_seq);
        return nullptr;
    }

    for (Py_ssize_t i = 0; i < n; ++i) {
        PyObject* pair_obj = PySequence_Fast_GET_ITEM(pair_seq, i);
        PyObject* pair = PySequence_Fast(pair_obj, "Each item must be a 4-length sequence");
        if (!pair) {
            Py_DECREF(result);
            Py_DECREF(pair_seq);
            return nullptr;
        }
        if (PySequence_Fast_GET_SIZE(pair) != 4) {
            Py_DECREF(pair);
            Py_DECREF(result);
            Py_DECREF(pair_seq);
            PyErr_SetString(PyExc_ValueError, "Each item must contain exactly 4 values");
            return nullptr;
        }

        const double lat1 = PyFloat_AsDouble(PySequence_Fast_GET_ITEM(pair, 0));
        const double lon1 = PyFloat_AsDouble(PySequence_Fast_GET_ITEM(pair, 1));
        const double lat2 = PyFloat_AsDouble(PySequence_Fast_GET_ITEM(pair, 2));
        const double lon2 = PyFloat_AsDouble(PySequence_Fast_GET_ITEM(pair, 3));

        if (PyErr_Occurred()) {
            Py_DECREF(pair);
            Py_DECREF(result);
            Py_DECREF(pair_seq);
            return nullptr;
        }

        try {
            PyObject* d = PyFloat_FromDouble(vincenty_distance_m(lat1, lon1, lat2, lon2));
            if (!d) {
                Py_DECREF(pair);
                Py_DECREF(result);
                Py_DECREF(pair_seq);
                return nullptr;
            }
            PyList_SET_ITEM(result, i, d);
        } catch (const std::exception& ex) {
            Py_DECREF(pair);
            Py_DECREF(result);
            Py_DECREF(pair_seq);
            PyErr_SetString(PyExc_RuntimeError, ex.what());
            return nullptr;
        }

        Py_DECREF(pair);
    }

    Py_DECREF(pair_seq);
    return result;
}

PyObject* py_gcj02_to_wgs84_batch(PyObject* /*self*/, PyObject* args) {
    PyObject* point_list_obj = nullptr;
    if (!PyArg_ParseTuple(args, "O", &point_list_obj)) {
        return nullptr;
    }

    PyObject* point_seq = PySequence_Fast(point_list_obj, "Expected a sequence of (lat, lon)");
    if (!point_seq) {
        return nullptr;
    }

    const Py_ssize_t n = PySequence_Fast_GET_SIZE(point_seq);
    PyObject* result = PyList_New(n);
    if (!result) {
        Py_DECREF(point_seq);
        return nullptr;
    }

    for (Py_ssize_t i = 0; i < n; ++i) {
        PyObject* point_obj = PySequence_Fast_GET_ITEM(point_seq, i);
        PyObject* point = PySequence_Fast(point_obj, "Each item must be a 2-length sequence");
        if (!point) {
            Py_DECREF(result);
            Py_DECREF(point_seq);
            return nullptr;
        }
        if (PySequence_Fast_GET_SIZE(point) != 2) {
            Py_DECREF(point);
            Py_DECREF(result);
            Py_DECREF(point_seq);
            PyErr_SetString(PyExc_ValueError, "Each item must contain exactly 2 values");
            return nullptr;
        }

        const double lat = PyFloat_AsDouble(PySequence_Fast_GET_ITEM(point, 0));
        const double lon = PyFloat_AsDouble(PySequence_Fast_GET_ITEM(point, 1));

        if (PyErr_Occurred()) {
            Py_DECREF(point);
            Py_DECREF(result);
            Py_DECREF(point_seq);
            return nullptr;
        }

        const auto converted = gcj02_to_wgs84_caijun(lat, lon);
        PyObject* converted_pair = Py_BuildValue("(dd)", converted.first, converted.second);
        if (!converted_pair) {
            Py_DECREF(point);
            Py_DECREF(result);
            Py_DECREF(point_seq);
            return nullptr;
        }

        PyList_SET_ITEM(result, i, converted_pair);
        Py_DECREF(point);
    }

    Py_DECREF(point_seq);
    return result;
}

PyMethodDef module_methods[] = {
    {"vincenty_distance_m", py_vincenty_distance_m, METH_VARARGS, "Compute Vincenty distance in meters."},
    {
        "vincenty_distance_batch_m",
        py_vincenty_distance_batch_m,
        METH_VARARGS,
        "Compute Vincenty distances for a batch of point pairs.",
    },
    {
        "gcj02_to_wgs84_batch",
        py_gcj02_to_wgs84_batch,
        METH_VARARGS,
        "Convert GCJ-02 coordinates to WGS84 for a batch of points.",
    },
    {nullptr, nullptr, 0, nullptr},
};

PyModuleDef module_def = {
    PyModuleDef_HEAD_INIT,
    "_vincenty",
    "C++ implementation of Vincenty distance",
    -1,
    module_methods,
};

}  // namespace

PyMODINIT_FUNC PyInit__vincenty(void) {
    return PyModule_Create(&module_def);
}
