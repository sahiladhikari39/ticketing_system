import { apiFetch, API_BASE_URL } from "./client";

function toFormData(data) {
  const formData = new FormData();
  Object.entries(data).forEach(([key, value]) => {
    if (value !== null && value !== undefined && value !== "") {
      formData.append(key, value);
    }
  });
  return formData;
}

export const ticketsApi = {
  list: () => apiFetch("/tickets/"),
  get: (id) => apiFetch(`/tickets/${id}/`),
  create: (data) => {
    // Multipart only when something is actually attached -- a
    // text-only ticket shouldn't pay for the encode.
    if (data.attachment instanceof File || data.video instanceof File) {
      return apiFetch("/tickets/", { method: "POST", body: toFormData(data) });
    }
    return apiFetch("/tickets/", { method: "POST", body: JSON.stringify(data) });
  },
  update: (id, data) =>
    apiFetch(`/tickets/${id}/`, { method: "PATCH", body: JSON.stringify(data) }),
  delete: (id) => apiFetch(`/tickets/${id}/`, { method: "DELETE" }),
  reports: () => apiFetch("/tickets/reports/"),
  // Field engineers for this ticket, ranked with whoever covers the
  // customer's own area first.
  nearbyEngineers: (id) => apiFetch(`/tickets/${id}/nearby-engineers/`),
};

export const commentsApi = {
  /**
   * `file` and `video` are both optional and independent. When
   * either is present, this builds real multipart
   * FormData so the file and the message are submitted TOGETHER, as
   * one request creating one TicketComment row -- not two separate
   * calls to two separate endpoints. When absent, plain JSON is used
   * instead, since there's no reason to pay for a multipart encode on
   * a text-only reply.
   */
  create: ({ ticket, body, is_internal_note, file, video }) => {
    if (file || video) {
      const formData = new FormData();
      formData.append("ticket", ticket);
      formData.append("body", body);
      formData.append("is_internal_note", is_internal_note ? "true" : "false");
      // Two independent slots -- a message can carry either, both, or
      // neither. Only append what's actually there.
      if (file) formData.append("attachment", file);
      if (video) formData.append("video", video);
      return apiFetch("/ticket-comments/", { method: "POST", body: formData });
    }
    return apiFetch("/ticket-comments/", {
      method: "POST",
      body: JSON.stringify({ ticket, body, is_internal_note }),
    });
  },
};

export const clientsApi = {
  list: () => apiFetch("/clients/"),
  get: (id) => apiFetch(`/clients/${id}/`),
  /**
   * `data.tax_document` may be a File object (from a <input type="file">)
   * or absent entirely. When present, this builds real multipart
   * FormData; otherwise plain JSON, same reasoning as commentsApi above.
   */
  create: (data) => {
    if (data.tax_document instanceof File) {
      return apiFetch("/clients/", { method: "POST", body: toFormData(data) });
    }
    return apiFetch("/clients/", { method: "POST", body: JSON.stringify(data) });
  },
  update: (id, data) => {
    if (data.tax_document instanceof File) {
      return apiFetch(`/clients/${id}/`, { method: "PATCH", body: toFormData(data) });
    }
    return apiFetch(`/clients/${id}/`, { method: "PATCH", body: JSON.stringify(data) });
  },
  delete: (id) => apiFetch(`/clients/${id}/`, { method: "DELETE" }),
};

export const staffRolesApi = {
  list: () => apiFetch("/staff-roles/"),
  create: (data) => apiFetch("/staff-roles/", { method: "POST", body: JSON.stringify(data) }),
  update: (id, data) => apiFetch(`/staff-roles/${id}/`, { method: "PATCH", body: JSON.stringify(data) }),
  delete: (id) => apiFetch(`/staff-roles/${id}/`, { method: "DELETE" }),
};

export const supportStaffApi = {
  list: () => apiFetch("/support-staff/"),
  create: (data) =>
    apiFetch("/support-staff/", { method: "POST", body: JSON.stringify(data) }),
  update: (userId, data) =>
    apiFetch(`/support-staff/${userId}/`, { method: "PATCH", body: JSON.stringify(data) }),
  delete: (userId) => apiFetch(`/support-staff/${userId}/`, { method: "DELETE" }),
};

export const subClientsApi = {
  list: () => apiFetch("/sub-clients/"),
  /**
   * Same reasoning as clientsApi.create/update above -- tax_document
   * may be a real File object now that Sub-Clients go through the
   * same document-required onboarding as Clients do.
   */
  create: (data) => {
    if (data.tax_document instanceof File) {
      return apiFetch("/sub-clients/", { method: "POST", body: toFormData(data) });
    }
    return apiFetch("/sub-clients/", { method: "POST", body: JSON.stringify(data) });
  },
  update: (userId, data) => {
    if (data.tax_document instanceof File) {
      return apiFetch(`/sub-clients/${userId}/`, { method: "PATCH", body: toFormData(data) });
    }
    return apiFetch(`/sub-clients/${userId}/`, { method: "PATCH", body: JSON.stringify(data) });
  },
  delete: (userId) => apiFetch(`/sub-clients/${userId}/`, { method: "DELETE" }),
};

export const auditLogApi = {
  list: () => apiFetch("/audit-logs/"),
};

export const meApi = {
  get: () => apiFetch("/me/"),
  changePassword: (data) =>
    apiFetch("/change-password/", { method: "POST", body: JSON.stringify(data) }),
};

export const passwordResetApi = {
  // Both callable while logged OUT -- someone resetting a password
  // can't authenticate first by definition. The emailed CODE is what
  // proves identity, so it's sent alongside the email it belongs to.
  request: (email) =>
    apiFetch("/password-reset/", { method: "POST", body: JSON.stringify({ email }) }),
  confirm: (email, code, newPassword) =>
    apiFetch("/password-reset/confirm/", {
      method: "POST",
      body: JSON.stringify({ email, code, new_password: newPassword }),
    }),
};

export const serviceReportsApi = {
  list: () => apiFetch("/service-reports/"),
  get: (id) => apiFetch(`/service-reports/${id}/`),
  /**
   * `video` is optional and, when present, forces multipart. Same
   * pattern as ticket comments -- plain JSON when there's no file, so
   * a text-only save doesn't pay for a multipart encode.
   */
  create: (data) => {
    if (data.service_video instanceof File) {
      return apiFetch("/service-reports/", { method: "POST", body: toFormData(data) });
    }
    return apiFetch("/service-reports/", { method: "POST", body: JSON.stringify(data) });
  },
  update: (id, data) => {
    if (data.service_video instanceof File) {
      return apiFetch(`/service-reports/${id}/`, { method: "PATCH", body: toFormData(data) });
    }
    return apiFetch(`/service-reports/${id}/`, { method: "PATCH", body: JSON.stringify(data) });
  },
  releaseToCustomer: (id) =>
    apiFetch(`/service-reports/${id}/release-to-customer/`, { method: "POST" }),
};

export const knowledgeBaseApi = {
  list: () => apiFetch("/knowledge-base/"),
};

export const accessCodesApi = {
  list: () => apiFetch("/access-codes/"),
  issue: (data) => apiFetch("/access-codes/", { method: "POST", body: JSON.stringify(data) }),
  // DELETE revokes rather than erases -- the record of who had access
  // survives, which is the point of an audit trail.
  revoke: (id) => apiFetch(`/access-codes/${id}/`, { method: "DELETE" }),
  /**
   * Deliberately NOT using apiFetch. Someone using an access code has
   * no JWT at all -- apiFetch's 401 handling (try a token refresh,
   * then hard-redirect to /login on failure) is built for an expired
   * REAL session, and would hijack a wrong-code error into a forced
   * redirect away from this page entirely before the person ever saw
   * why it failed. A plain fetch keeps this fully separate from the
   * account-login system, which is the whole point of access codes.
   */
  login: async (username, secret) => {
    const res = await fetch(`${API_BASE_URL}/access/login/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, secret }),
    });
    if (!res.ok) {
      let detail = "That code isn't valid.";
      try {
        const body = await res.json();
        detail = body.detail || detail;
      } catch {
        // keep the generic message
      }
      throw new Error(detail);
    }
    return res.json();
  },
};

export const historyAccessRequestsApi = {
  list: () => apiFetch("/history-access-requests/"),
  create: (ticketId, reason) =>
    apiFetch("/history-access-requests/", {
      method: "POST",
      body: JSON.stringify({ ticket: ticketId, reason }),
    }),
  approve: (id, hours) =>
    apiFetch(`/history-access-requests/${id}/approve/`, {
      method: "POST",
      body: JSON.stringify({ hours }),
    }),
  deny: (id) => apiFetch(`/history-access-requests/${id}/deny/`, { method: "POST" }),
};
