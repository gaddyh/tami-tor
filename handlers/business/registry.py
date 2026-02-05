from handlers.business.tami_tor import tami_tor_handler
from handlers.business.tami_tor_dev import tami_tor_dev_handler
from handlers.business.tami import tami_handler

tami_wa_id = "723503380842690"
tami_dev_wa_id = "816205444920021"
tami_tor_wa_id = "982974261547358"


wa_phone_id_registry = {
    tami_wa_id: tami_handler,
    tami_dev_wa_id: tami_tor_dev_handler,
    tami_tor_wa_id: tami_tor_handler,
}
