import os
import py_compile


def test_streamlit_pages_compile():
    bad = []
    for root, _, files in os.walk("streamlit_app/pages"):
        for f in files:
            if not f.endswith(".py"):
                continue
            p = os.path.join(root, f)
            try:
                py_compile.compile(p, doraise=True)
            except Exception as e:
                bad.append((p, str(e)))

    assert not bad, f"Streamlit page syntax errors: {bad}"
