# payments/views/

Payment views split by responsibility.

## Modules

| File | Responsibility |
|------|---------------|
| `initiation.py` | `initiate_payment`, `check_payment_status`, `list_payments` + `convert_to_dict` helper |
| `refunds.py` | `initiate_refund` — admin/host-only refund initiation |
| `callbacks.py` | `phonepe_callback` — PhonePe webhook handler (CSRF-exempt, handles payment + refund events) |
| `__init__.py` | Re-exports all functions so `payments/urls.py` (`from . import views; views.function_name`) works unchanged |

## Notes

- `callbacks.py` is the most complex module — it handles two event flows per payment type:
  - **Invite-based flow** (new): looks up existing `TournamentRegistration` by `udf4` and calls `process_successful_registration`
  - **Legacy flow** (old): reads `registration_data` from `meta_info` and creates team + registration from scratch
- Both `check_payment_status` and `phonepe_callback` implement idempotency checks to avoid duplicate tournament/registration creation
