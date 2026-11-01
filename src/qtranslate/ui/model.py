import threading


class DashboardModel:
    def __init__(self, settings, store):
        self.settings = settings
        self.store = store
        self._audit_lock = threading.Lock()

    def translator_status(self):
        credentials = self.store.translation_credentials(verified=False)
        verified = [c for c in credentials if c.get("status") == "translation_verified"]
        return {
            "verified": len(verified),
            "pending": len(credentials) - len(verified),
            "credentials": [
                {
                    "id": c["id"],
                    "region": c.get("region", "global"),
                    "verified": c.get("status") == "translation_verified",
                }
                for c in credentials
            ],
        }

    def save_translator(self, key, region="global", verifier=None):
        from qtranslate.config.secrets import translation_credential
        from qtranslate.providers.azure_translator import AzureTranslator
        from qtranslate.audit.legacy import now

        credential = translation_credential(key, region)
        (verifier or AzureTranslator.probe)(credential["key"], credential["region"])
        credential.update(status="translation_verified", verified_at=now())
        report = self.store.merge(
            {
                "format": "qtranslate-portable",
                "version": 1,
                "providers": [
                    {
                        "id": "azure_translator",
                        "models": [],
                        "credentials": [credential],
                    }
                ],
            }
        )
        settings = self.settings.load()
        settings["translation_provider"] = "azure_translator"
        self.settings.save(settings)
        return report

    def verify_translators(self, verifier=None):
        verified, errors = 0, []
        for credential in self.store.translation_credentials(verified=False):
            if credential.get("status") == "translation_verified":
                continue
            try:
                self.save_translator(
                    credential["key"], credential.get("region", "global"), verifier
                )
                verified += 1
            except (RuntimeError, ValueError) as error:
                from qtranslate.providers.azure_translator import ERRORS

                errors.append(
                    {
                        "id": credential["id"],
                        "error": str(error)
                        if str(error) in ERRORS
                        else "AZURE_UNAVAILABLE",
                    }
                )
        return {"verified": verified, "errors": errors}

    def providers(self, capability="text"):
        settings = self.settings.load()
        candidates = self.store.candidates(
            capability,
            settings["vision_order" if capability == "vision" else "provider_order"],
        )
        data = self.store.load()
        rows = []
        for pid in settings[
            "vision_order" if capability == "vision" else "provider_order"
        ]:
            items = [c for c in candidates if c.provider == pid]
            p = next(
                (p for p in data["providers"] if p["id"] == pid), {"credentials": []}
            )
            rows.append(
                {
                    "id": pid,
                    "models": list(dict.fromkeys(c.model for c in items)),
                    "count": len({c.credential.id for c in items}),
                    "total": len(p["credentials"]),
                    "enabled": settings.get(
                        "vision_enabled" if capability == "vision" else "enabled",
                        settings["enabled"],
                    ).get(pid, True),
                    "ids": [c["id"] for c in p["credentials"]],
                }
            )
        return rows

    def toggle(self, provider, enabled, capability="text"):
        settings = self.settings.load()
        settings.setdefault(
            "vision_enabled" if capability == "vision" else "enabled", {}
        )[provider] = enabled
        self.settings.save(settings)

    def move(self, provider, delta, capability="text"):
        settings = self.settings.load()
        order = settings["vision_order" if capability == "vision" else "provider_order"]
        i = order.index(provider)
        j = i + delta
        if 0 <= j < len(order):
            order[i], order[j] = order[j], order[i]
            self.settings.save(settings)

    def choose(self, provider, model, capability="text"):
        if not any(
            row["id"] == provider and model in row["models"]
            for row in self.providers(capability)
        ):
            raise ValueError("MODEL_NOT_VERIFIED")
        settings = self.settings.load()
        settings.setdefault(
            "vision_selected_models" if capability == "vision" else "selected_models",
            {},
        )[provider] = model
        self.settings.save(settings)

    def audit_new(self, runner=None):
        if not self._audit_lock.acquire(blocking=False):
            raise ValueError("AUDIT_RUNNING")
        try:
            return self._audit_new(runner)
        finally:
            self._audit_lock.release()

    def _audit_new(self, runner=None):
        import copy
        from qtranslate.audit.legacy import audit, apply_audit

        data = self.store.load()
        bundle = copy.deepcopy(data)
        bundle["format"] = "qtranslate-portable"
        for provider in bundle["providers"]:
            provider["credentials"] = [
                c
                for c in provider["credentials"]
                if not c.get("capabilities")
                and c.get("status") != "capability_verified"
            ]
        bundle["providers"] = [
            p
            for p in bundle["providers"]
            if p["credentials"] and p["id"] != "azure_translator"
        ]
        if not bundle["providers"]:
            return {"status": "nothing_to_probe", "credentials": []}
        report = (runner or audit)(bundle)
        verified = apply_audit(bundle, report)
        self.store.merge(verified)
        bad = {
            r["credential_id"]
            for r in report["credentials"]
            if r["status"] == "invalid_auth_confirmed"
        }
        if bad:
            self.store.remove_invalid(bad)
        return report
