/** @odoo-module **/

import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";

async function directPrintAction(env, action) {
    const { params } = action;
    const attachments = params.attachments || [];

    if (!attachments.length) {
        env.services.notification.add(_t("No document found to print."), { type: "warning" });
        return;
    }

    for (const item of attachments) {
        try {
            env.services.notification.add(
                _t("Sending '%s' to printer...", item.name || "Document"),
                { type: "info" }
            );

            await printDocumentUrl(item.url, item.mimetype);
        } catch (err) {
            console.error("Direct Print Error:", err);
            env.services.notification.add(
                _t("Failed to print '%s': %s", item.name || "Document", err.message || err),
                { type: "danger" }
            );
        }
    }
}

function printDocumentUrl(url, mimetype) {
    return new Promise((resolve, reject) => {
        const iframe = document.createElement("iframe");
        iframe.style.position = "fixed";
        iframe.style.right = "0";
        iframe.style.bottom = "0";
        iframe.style.width = "0";
        iframe.style.height = "0";
        iframe.style.border = "0";
        iframe.style.visibility = "hidden";

        document.body.appendChild(iframe);

        const cleanup = () => {
            setTimeout(() => {
                if (iframe && iframe.parentNode) {
                    iframe.parentNode.removeChild(iframe);
                }
            }, 3000);
        };

        const triggerPrint = () => {
            try {
                iframe.contentWindow.focus();
                iframe.contentWindow.print();
                cleanup();
                resolve();
            } catch (err) {
                cleanup();
                reject(err);
            }
        };

        if (mimetype && mimetype.startsWith("image/")) {
            const htmlContent = `
                <!DOCTYPE html>
                <html>
                <head>
                    <style>
                        body { margin: 0; display: flex; justify-content: center; align-items: center; }
                        img { max-width: 100%; max-height: 100vh; object-fit: contain; }
                    </style>
                </head>
                <body>
                    <img src="${url}" onload="window.print();" />
                </body>
                </html>
            `;
            iframe.contentDoc.write(htmlContent);
            iframe.contentDoc.close();
            setTimeout(() => {
                cleanup();
                resolve();
            }, 1000);
        } else {
            // PDF or standard document
            iframe.src = url;
            iframe.onload = () => {
                setTimeout(triggerPrint, 500);
            };
        }
    });
}

registry.category("actions").add("yohannes_direct_print_action", directPrintAction);
