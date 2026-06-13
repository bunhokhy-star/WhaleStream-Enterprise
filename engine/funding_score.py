def funding_points(funding):

    if funding > 0.001:
        return -20

    if funding > 0.0005:
        return -10

    if funding < -0.001:
        return 20

    if funding < -0.0005:
        return 10

    return 0