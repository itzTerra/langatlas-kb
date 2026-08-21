from datetime import date

from langatlas_validate.publish_cli import data_vn_tag_for_today


def test_data_vn_tag_is_date_stamped():
    tag = data_vn_tag_for_today(today=date(2026, 8, 21))
    assert tag == "data-v2026.08.21"
