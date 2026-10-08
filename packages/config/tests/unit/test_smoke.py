def test_package_imports() -> None:
    import newsdock_config

    assert newsdock_config.__name__ == "newsdock_config"
