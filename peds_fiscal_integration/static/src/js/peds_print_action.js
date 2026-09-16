/** @odoo-module **/

import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";

// Polyfill for older Chrome versions (older than v110) used on POS machines
if (!Array.prototype.toReversed) {
    Object.defineProperty(Array.prototype, 'toReversed', {
        value: function() {
            return this.slice().reverse();
        },
        enumerable: false,
        configurable: true,
        writable: true
    });
}

async function pedsFiscalPrintAction(env, action) {
    const { params } = action;
    // For backward compatibility, default method to POST if payload is present
    let { api_url, endpoint, payload, method, query_params, success_msg, is_wizard } = params;
    
    // If the request comes from the wizard, build the routes in JS
    let api_key = params.api_key || "";
    let auth_license_key = params.auth_license_key || api_key;
    
    if (is_wizard) {
        // All wizard operations go to /pedsfpsrv/api/SalesInvoice/<action_type>
        // Server uses lowercase endpoints — normalize action_type to lowercase
        const base_url = (params.base_url || api_url || "").replace(/\/+$/, "");
        api_url = `${base_url}/pedsfpsrv/api/SalesInvoice`;
        // Always lowercase the endpoint — server uses e.g. getinvoiceprintstatus, setinvoiceasprinted
        const actionTypeLower = params.action_type.toLowerCase();
        endpoint = `/${actionTypeLower}`;
        method = 'GET';
        payload = false;
        query_params = false;

        if (['printfullfiscalreportbyz', 'printsummaryfiscalreportbyz'].includes(actionTypeLower)) {
            query_params = { 'fromZ': String(params.from_z), 'toZ': String(params.to_z) };
        } else if (['printfullfiscalreportbydate', 'printsummaryfiscalreportbydate'].includes(actionTypeLower)) {
            query_params = { 'dateFrom': params.date_from, 'dateTo': params.date_to };
        } else if (actionTypeLower === 'getinvoiceprintstatus') {
            // Reference: GET with JSON body (pos_wizards.py uses requests.get(..., json=payload))
            method = 'GET';
            payload = {
                "ThirdPartyID": "Odoo",
                "TenantId": params.tenant_id,
                "TransactionID": params.transaction_id
            };
        } else if (actionTypeLower === 'setinvoiceasprinted') {
            method = 'POST';
            payload = {
                "ThirdPartyID": "Odoo",
                "TenantId": params.tenant_id,
                "TransactionID": params.transaction_id,
                "FPMachineId": params.fp_machine_id,
                "FSInvoiceNumber": params.fs_invoice_number,
                "EJNumber": params.ej_number,
                "DatePrinted": params.date_printed
            };
        } else if (actionTypeLower === 'registerlicensekeys') {
            method = 'POST';
            endpoint = '/PrintInvoice/RegisterLicenseKeys';
            const rawKeys = params.license_keys || "";
            payload = { 
                "licensekeys": rawKeys,
                " licensekeys": rawKeys
            };
            success_msg = _t("License keys registered successfully!");
            console.log("=== RegisterLicenseKeys PAYLOAD ===", JSON.stringify(payload));
        }
        
        if (!success_msg) {
            success_msg = _t('Operation completed successfully!');
        }
    } else if (params.invoice_data) {
        // Compatibility with old action signature from Invoice Print button
        payload = params.invoice_data;
        endpoint = "/PrintInvoice";
        method = "POST";
        success_msg = _t("Invoice printed successfully!");
    }

    try {
        // Build the final URL
        let url = (api_url || "").trim().replace(/\/+$/, "");
        if (endpoint) {
            const cleanEndpoint = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
            if (!url.toLowerCase().endsWith(cleanEndpoint.toLowerCase())) {
                url = `${url}${cleanEndpoint}`;
            }
        }

        const isRegisterLicense = endpoint === '/PrintInvoice/RegisterLicenseKeys';
        query_params = Object.assign({}, query_params || {});
        if (api_key) {
            query_params["ApiKey"] = api_key;
        }
        if (auth_license_key && !isRegisterLicense) {
            query_params["LicenseKey"] = auth_license_key;
            query_params["LicenseKeys"] = auth_license_key;
        }

        if (Object.keys(query_params).length > 0) {
            const searchParams = new URLSearchParams(query_params);
            url += '?' + searchParams.toString();
        }

        const headers = {
            "Content-Type": "application/json",
            "Accept": "*/*"
        };
        if (api_key) {
            headers["ApiKey"] = api_key;
            headers["X-API-Key"] = api_key;
            headers["api_key"] = api_key;
        }
        if (auth_license_key) {
            headers["LicenseKey"] = auth_license_key;
            headers["LicenseKeys"] = auth_license_key;
        }

        const fetchOptions = {
            method: method || (payload ? "POST" : "GET"),
            headers: headers
        };

        if (payload) {
            fetchOptions.body = JSON.stringify(payload);
        }

        // --- Debug Logging ---
        console.log("=== PEDS API REQUEST ===");
        console.log("URL:", url);
        console.log("Method:", fetchOptions.method);
        if (payload) {
            console.log("Payload:", payload);
        }
        console.log("========================");
        // ---------------------

        const response = await fetch(url, fetchOptions);
        
        // Check if the response is actually JSON before parsing
        const contentType = response.headers.get("content-type");
        if (!contentType || !contentType.includes("application/json")) {
            const textResponse = await response.text();
            throw new Error(`Server returned a non-JSON response (Status ${response.status}). Is the URL correct?`);
        }

        const result = await response.json();

        // Standardize success checking since PEDS might return Success or PrintStatus
        let isSuccess = result.Success === "true" || result.Success === true || result.PrintStatus === "true" || result.PrintStatus === true;

        // Extract fiscal content fields supporting both PascalCase and camelCase / mixed variations
        const content = result.Content || result.content || {};
        const fpMachineId = content.FPMachineID || content.FpMachineId || content.fpMachineId || content.FPMachineId || false;
        const fsInvoiceNumber = content.FSInvoiceNumber || content.FsInvoiceNumber || content.fsInvoiceNumber || false;
        const ejNumber = content.EJNumber || content.EjNumber || content.ejNumber || false;
        const timeStamp = content.TimeStamp || content.timestamp || content.DatePrinted || false;

        // PEDS returns Success="false" if an invoice was already printed.
        // Check if message indicates it was already printed
        const msg = (result.ShortMessage || result.PrintMessage || result.Message || result.ErrorDetail || "").toLowerCase();
        const isAlreadyPrintedMsg = msg.includes("already") || msg.includes("printed");

        if (!isSuccess && (fpMachineId || isAlreadyPrintedMsg)) {
            isSuccess = true;
            success_msg = result.ShortMessage || result.PrintMessage || result.Message || _t("Invoice already printed!");
        }

        if (isSuccess) {
            env.services.notification.add(success_msg || _t("Operation completed successfully!"), { type: "success" });
            
            // Mark invoice printed if it was an invoice print operation or status check
            if ((endpoint === "/PrintInvoice" || endpoint === "/getinvoiceprintstatus") && payload && payload.TransactionID) {
                try {
                    await env.services.orm.call("account.move", "mark_peds_printed", [
                        payload.TransactionID, 
                        fpMachineId || "PEDS-FP", 
                        fsInvoiceNumber || false, 
                        ejNumber || false, 
                        timeStamp || false
                    ]);
                    env.services.action.doAction({ type: 'ir.actions.client', tag: 'reload' });
                } catch (ormError) {
                    console.error("Failed to mark invoice as printed in Odoo:", ormError);
                    const errorDetail = ormError.data?.message || ormError.message || String(ormError);
                    env.services.notification.add(
                        _t("Invoice printed on fiscal printer, but updating Odoo record failed: ") + errorDetail,
                        { type: "warning", sticky: true }
                    );
                }
            } else if (endpoint === "/RegisterLicenseKeys" && payload && payload.licensekeys) {
                // Permanently save the successfully registered keys on the company model
                await env.services.orm.call("res.company", "save_peds_license", [payload.licensekeys]);
            } else if (endpoint === "/setinvoiceasprinted" && payload && payload.TransactionID) {
                try {
                    await env.services.orm.call("account.move", "mark_peds_printed", [
                        payload.TransactionID, 
                        payload.FPMachineId, 
                        payload.FSInvoiceNumber, 
                        payload.EJNumber, 
                        payload.DatePrinted
                    ]);
                    env.services.notification.add(_t("Invoice forcefully marked as printed."), { type: "success" });
                    env.services.action.doAction({ type: 'ir.actions.client', tag: 'reload' });
                } catch (ormError) {
                    console.error("Failed to force mark invoice as printed:", ormError);
                }
            }
        } else {
            const errorMsg = result.ErrorDetail || result.PrintMessage || result.Message || result.ShortMessage || _t("Unknown error");
            env.services.notification.add(
                errorMsg,
                { type: 'danger', title: _t("Operation Failed") }
            );
        }
    } catch (error) {
        console.error("PEDS API Error:", error);
        const errMsg = error.message || error.data?.message || String(error);
        env.services.notification.add(
            _t("PEDS Fiscal Integration Error (") + api_url + _t("): ") + errMsg,
            { type: "danger", sticky: true }
        );
    }
    
    return undefined;
}

registry.category("actions").add("peds_fiscal_print", pedsFiscalPrintAction);
