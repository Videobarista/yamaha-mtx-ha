"""Config flow for the Yamaha MTX integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv

from .client import DeviceInfo, RcpError
from .const import (
    CONF_MODEL,
    DEFAULT_OPTIONS,
    DEFAULT_PORT,
    DOMAIN,
    OPT_DCA,
    OPT_INPUTS,
    OPT_MATRIX,
    OPT_OUTPUTS,
    OPT_ROUTER,
    OPT_ZONES,
)
from .device import MtxDevice, MtxUnsupportedModelError

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): cv.port,
    }
)

OPTION_KEYS = (OPT_INPUTS, OPT_ZONES, OPT_OUTPUTS, OPT_ROUTER, OPT_DCA, OPT_MATRIX)


async def _async_probe(host: str, port: int) -> DeviceInfo:
    """Connect once, read the device info and disconnect."""
    device = MtxDevice(host, port, {})
    try:
        return await device.async_setup()
    finally:
        await device.async_shutdown()


class MtxConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Yamaha MTX."""

    VERSION = 1

    async def _async_validate(
        self, user_input: dict[str, Any]
    ) -> tuple[DeviceInfo | None, dict[str, str], dict[str, str]]:
        """Probe the device. Returns (info, errors, description placeholders)."""
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}
        try:
            info = await _async_probe(user_input[CONF_HOST], user_input[CONF_PORT])
        except MtxUnsupportedModelError as err:
            errors["base"] = "unsupported_model"
            placeholders["model"] = err.model
        except RcpError as err:
            _LOGGER.debug("Cannot connect to %s: %s", user_input[CONF_HOST], err)
            errors["base"] = "cannot_connect"
        except Exception:
            _LOGGER.exception("Unexpected error while connecting to the MTX")
            errors["base"] = "unknown"
        else:
            return info, errors, placeholders
        return None, errors, placeholders

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for host and port."""
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {"model": ""}
        if user_input is not None:
            user_input = {**user_input, CONF_HOST: user_input[CONF_HOST].strip()}
            info, errors, found = await self._async_validate(user_input)
            placeholders.update(found)
            if info is not None:
                await self.async_set_unique_id(info.serial or user_input[CONF_HOST])
                self._abort_if_unique_id_configured(updates=user_input)
                return self.async_create_entry(
                    title=info.name or info.product,
                    data={**user_input, CONF_MODEL: info.product},
                    options=dict(DEFAULT_OPTIONS),
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_SCHEMA, user_input
            ),
            errors=errors,
            description_placeholders=placeholders,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change host or port of an existing entry."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {"model": ""}
        if user_input is not None:
            user_input = {**user_input, CONF_HOST: user_input[CONF_HOST].strip()}
            info, errors, found = await self._async_validate(user_input)
            placeholders.update(found)
            if info is not None:
                await self.async_set_unique_id(info.serial or user_input[CONF_HOST])
                self._abort_if_unique_id_mismatch(reason="wrong_device")
                return self.async_update_reload_and_abort(
                    entry, data_updates={**user_input, CONF_MODEL: info.product}
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_SCHEMA, user_input or entry.data
            ),
            errors=errors,
            description_placeholders=placeholders,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> MtxOptionsFlow:
        """Return the options flow."""
        return MtxOptionsFlow()


class MtxOptionsFlow(OptionsFlow):
    """Choose which entity groups to create."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the entity group toggles."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current = {**DEFAULT_OPTIONS, **self.config_entry.options}
        schema = vol.Schema(
            {vol.Required(key, default=bool(current[key])): bool for key in OPTION_KEYS}
        )
        return self.async_show_form(step_id="init", data_schema=schema)
