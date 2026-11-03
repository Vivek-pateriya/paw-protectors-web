import React, { useEffect, useId, useRef, useState } from "react";
import { request } from "./api";

const label = (value) => String(value ?? "").replaceAll("_", " ");
const when = (value) => new Date(value).toLocaleString();
const editableStates = ["pending_review", "available", "rejected"];
const listingFields = [
  ["name", "Animal name", "text", true, 120],
  ["species", "Species", "text", true, 100],
  ["breed", "Breed", "text", false, 120],
  ["age_months", "Age in months", "number", true, 1200],
  ["gender", "Gender", "select", true, ["unknown", "male", "female"]],
  ["location", "City / location", "text", true, 200],
  ["description", "About this animal", "textarea", true, 5000],
  ["health_summary", "Health summary", "textarea", false, 5000],
  ["weight_kg", "Weight in kg (optional)", "number", false, 2000],
  ["allergies", "Allergies", "textarea", false, 5000],
];
const applicationFields = [
  ["motivation", "Why would you like to adopt?", "textarea", true, 2000],
  [
    "housing",
    "Home type",
    "select",
    true,
    ["house", "apartment", "farm", "other"],
  ],
  [
    "has_other_pets",
    "Do you have other pets?",
    "select",
    true,
    ["false", "true"],
  ],
  ["experience", "Pet-care experience", "textarea", false, 2000],
  [
    "contact_phone",
    "Contact phone (visible to administrators)",
    "tel",
    false,
    30,
  ],
];

function Photo({ row, token, detail = false }) {
  const [src, setSrc] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    let url,
      active = true;
    setSrc("");
    if (row.image_path)
      fetch(`/adoption/listings/${row.id}/image?v=${row.version}`, {
        headers: { Authorization: `Bearer ${token}` },
        signal: controller.signal,
      })
        .then((r) => {
          if (!r.ok) throw new Error();
          return r.blob();
        })
        .then((blob) => {
          if (active) {
            url = URL.createObjectURL(blob);
            setSrc(url);
          }
        })
        .catch(() => {});
    return () => {
      active = false;
      controller.abort();
      if (url) URL.revokeObjectURL(url);
    };
  }, [row.id, row.image_path, row.version, token]);
  return (
    <div className={`pet-face${detail ? ' photo-detail' : ''}`}>
      {src ? (
        <img src={src} alt={row.name} />
      ) : (
        <span aria-label="No animal photo">🐾</span>
      )}
    </div>
  );
}

function Editor({ listing, application = false, onSave, onCancel }) {
  const formId = useId(),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const fields = application ? applicationFields : listingFields;
  return (
    <article className="card">
      <h2>
        {application
          ? "Adoption application"
          : listing.id
            ? "Edit adoption listing"
            : "Add an animal for adoption"}
      </h2>
      {!application && (
        <p>
          Owner submissions and changes need administrator approval before
          publication. Add a photo after saving.
        </p>
      )}
      <form
        onSubmit={async (event) => {
          event.preventDefault();
          setBusy(true);
          setError("");
          try {
            const values = Object.fromEntries(
              new FormData(event.currentTarget),
            );
            if (application)
              values.has_other_pets = values.has_other_pets === "true";
            else {
              values.age_months = Number(values.age_months);
              values.weight_kg =
                values.weight_kg === "" ? null : Number(values.weight_kg);
            }
            await onSave(values);
          } catch (e) {
            setError(e.message);
          } finally {
            setBusy(false);
          }
        }}
      >
        {fields.map(([name, title, type, required, maximum]) => {
          const props = {
            id: `${formId}-${name}`,
            name,
            required,
            disabled: busy,
            defaultValue:
              listing[name] ??
              (name === "species"
                ? "Dog"
                : name === "age_months"
                  ? 0
                  : name === "gender"
                    ? "unknown"
                    : name === "housing"
                      ? "house"
                      : name === "has_other_pets"
                        ? "false"
                        : ""),
            maxLength:
              type === "number" || type === "select" ? undefined : maximum,
          };
          return (
            <React.Fragment key={name}>
              <label htmlFor={props.id}>
                {title}
                {required ? " *" : ""}
              </label>
              {type === "textarea" ? (
                <textarea
                  {...props}
                  minLength={name === "motivation" ? 10 : undefined}
                />
              ) : type === "select" ? (
                <select {...props}>
                  {maximum.map((option) => (
                    <option key={option} value={option}>
                      {option === "true"
                        ? "Yes"
                        : option === "false"
                          ? "No"
                          : label(option)}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  {...props}
                  type={type}
                  min={name === "weight_kg" ? 0.001 : 0}
                  max={type === "number" ? maximum : undefined}
                  step={name === "weight_kg" ? 0.001 : 1}
                />
              )}
            </React.Fragment>
          );
        })}
        {error && (
          <p className="inline-error" role="alert">
            {error}
          </p>
        )}
        <div className="actions">
          <button className="btn" disabled={busy}>
            {busy
              ? "Saving…"
              : application
                ? "Submit application"
                : "Save listing"}
          </button>
          <button
            className="btn ghost"
            type="button"
            disabled={busy}
            onClick={onCancel}
          >
            Cancel
          </button>
        </div>
      </form>
    </article>
  );
}

function ReviewDialog({ decision, onCancel, onSubmit }) {
  const ref = useRef(),
    id = useId(),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  useEffect(() => {
    ref.current.showModal();
  }, []);
  return (
    <dialog
      ref={ref}
      aria-labelledby={id}
      onCancel={(event) => {
        event.preventDefault();
        if (!busy) onCancel();
      }}
    >
      <h2 id={id}>{decision.title}</h2>
      <p>{decision.message}</p>
      <form
        onSubmit={async (event) => {
          event.preventDefault();
          const reason = String(
            new FormData(event.currentTarget).get("reason") || "",
          ).trim();
          if (decision.action === "reject" && !reason) {
            setError("A rejection reason is required.");
            return;
          }
          setBusy(true);
          setError("");
          try {
            await onSubmit(reason);
          } catch (e) {
            setError(e.message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <label htmlFor={id + "-reason"}>
          {decision.action === "reject"
            ? "Rejection reason *"
            : "Note (optional)"}
        </label>
        <textarea
          id={id + "-reason"}
          name="reason"
          maxLength={2000}
          required={decision.action === "reject"}
          disabled={busy}
        />
        {error && (
          <p role="alert" className="inline-error">
            {error}
          </p>
        )}
        <div className="form-actions">
          <button
            className="btn ghost"
            type="button"
            disabled={busy}
            onClick={onCancel}
          >
            Keep unchanged
          </button>
          <button className="btn" type="submit" disabled={busy}>
            {busy ? "Saving…" : "Confirm decision"}
          </button>
        </div>
      </form>
    </dialog>
  );
}

export function AdoptionPage({ user, token, onExpired }) {
  const [view, setView] = useState("browse"),
    [selection, updateSelection] = useState(null),
    [editor, setEditor] = useState(null);
  const [confirmation, setConfirmation] = useState(null);
  const [data, setData] = useState(null),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0),
    [offset, setOffset] = useState(0),
    [listingFilter, setListingFilter] = useState(null);
  const [filters, setFilters] = useState({
    q: "",
    species: "",
    location: "",
    max_age_months: "",
    status: "",
  });
  const admin = user.role === "admin",
    owner = user.role === "owner";
  function setSelection(next) {
    setData(null);
    updateSelection(next);
  }
  const refresh = () => setRevision((x) => x + 1);
  const api = async (path, method = "GET", body, signal) => {
    try {
      return await request(path, token, method, body, signal);
    } catch (e) {
      if (e.status === 401) onExpired();
      throw e;
    }
  };
  function tab(next, listingId = null) {
    setView(next);
    setSelection(null);
    setEditor(null);
    setOffset(0);
    setListingFilter(listingId);
    setFilters({
      q: "",
      species: "",
      location: "",
      max_age_months: "",
      status: "",
    });
    setError("");
    setNotice("");
  }
  useEffect(() => {
    const c = new AbortController();
    let active = true;
    setData(null);
    setError("");
    let path;
    if (selection)
      path = `/adoption/${selection.type === "listing" ? "listings" : "applications"}/${selection.id}`;
    else {
      const apps = ["applications", "review"].includes(view),
        params = new URLSearchParams({
          scope: apps
            ? view === "review"
              ? "review"
              : "mine"
            : view === "moderation"
              ? "review"
              : view === "mine"
                ? "mine"
                : "browse",
          offset: String(offset),
          limit: "12",
        });
      for (const [key, value] of Object.entries(filters))
        if (value !== "" && (apps ? key === "status" : true))
          params.set(key, value);
      if (apps && listingFilter)
        params.set("listing_id", String(listingFilter));
      path = `/adoption/${apps ? "applications" : "listings"}?${params}`;
    }
    api(path, "GET", undefined, c.signal)
      .then((result) => {
        if (active) setData(result);
      })
      .catch((e) => {
        if (active && !c.signal.aborted) setError(e.message);
      });
    return () => {
      active = false;
      c.abort();
    };
  }, [view, selection, filters, offset, listingFilter, revision, token]);
  async function act(fn, message) {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await fn();
      setNotice(message);
      refresh();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  function review(action) {
    setConfirmation({
      entity: "listing",
      id: data.id,
      version: data.version,
      action,
      title:
        action === "approve"
          ? "Approve publication?"
          : action === "reject"
            ? "Reject listing?"
            : "Archive listing?",
      message:
        action === "approve"
          ? "Publish this animal for adoption."
          : action === "reject"
            ? "The submitter can revise the listing and submit it again."
            : "Pending applications will be closed and history retained.",
    });
  }
  function decide(action) {
    setConfirmation({
      entity: "application",
      id: data.id,
      action,
      title: {
        approve: "Approve and reserve?",
        reject: "Reject application?",
        complete: "Confirm handover completed?",
        withdraw: "Withdraw application?",
      }[action],
      message: {
        approve: "Reserve this animal for this applicant.",
        reject: "An approved reservation will be released.",
        complete:
          "Confirm the animal has been handed over. A pet profile will be created for this adopter.",
        withdraw: "Any reservation will be released.",
      }[action],
    });
  }
  const buttons = [
    ["browse", "Find a companion"],
    ...(owner || admin ? [["mine", "My listings"]] : []),
    ...(owner ? [["applications", "My applications"]] : []),
    ...(admin
      ? [
          ["moderation", "Listing approvals"],
          ["review", "Application review"],
        ]
      : []),
  ];
  return (
    <section>
      {confirmation && (
        <ReviewDialog
          decision={confirmation}
          onCancel={() => setConfirmation(null)}
          onSubmit={async (reason) => {
            await api(
              `/adoption/${confirmation.entity === "listing" ? "listings" : "applications"}/${confirmation.id}/${confirmation.entity === "listing" ? "review" : "decision"}`,
              "POST",
              {
                action: confirmation.action,
                reason,
                ...(confirmation.entity === "listing"
                  ? { version: confirmation.version }
                  : {}),
              },
            );
            setConfirmation(null);
            setNotice("Decision saved.");
            refresh();
          }}
        />
      )}
      <div className="page-header">
        <div>
          <h1>Adoption</h1>
          <p>A new home. A new beginning.</p>
        </div>
        {(owner || admin) && (
          <button
            className="btn"
            disabled={busy}
            onClick={() => {
              setEditor({ type: "listing", row: {} });
              setError("");
            }}
          >
            + List an animal
          </button>
        )}
      </div>
      <div className="actions" role="navigation" aria-label="Adoption views">
        {buttons.map(([key, title]) => (
          <button
            key={key}
            className={`btn ${view === key ? "" : "secondary"}`}
            aria-pressed={view === key}
            disabled={busy}
            onClick={() => tab(key)}
          >
            {title}
          </button>
        ))}
      </div>
      {!!notice && <p role="status">{notice}</p>}
      {!!error && (
        <p role="alert" className="inline-error">
          {error}
        </p>
      )}
      {editor ? (
        <Editor
          key={editor.type + String(editor.row.id || "new")}
          listing={editor.row}
          application={editor.type === "application"}
          onCancel={() => setEditor(null)}
          onSave={async (values) => {
            if (editor.type === "application") {
              const result = await api(
                `/adoption/listings/${editor.row.id}/applications`,
                "POST",
                values,
              );
              setView("applications");
              setSelection({ type: "application", id: result.id });
              setNotice("Application submitted for administrator review.");
            } else {
              const result = await api(
                editor.row.id
                  ? `/adoption/listings/${editor.row.id}`
                  : "/adoption/listings",
                editor.row.id ? "PUT" : "POST",
                {
                  ...values,
                  ...(editor.row.id ? { version: editor.row.version } : {}),
                },
              );
              setView("mine");
              setSelection({ type: "listing", id: result.id });
              setNotice(
                result.status === "pending_review"
                  ? "Listing submitted. It will appear publicly after admin approval."
                  : "Listing saved.",
              );
            }
            setEditor(null);
            refresh();
          }}
        />
      ) : (
        <>
          {!selection && (
            <form
              className="card"
              key={view}
              onSubmit={(event) => {
                event.preventDefault();
                const f = Object.fromEntries(new FormData(event.currentTarget));
                setFilters({
                  q: "",
                  species: "",
                  location: "",
                  max_age_months: "",
                  status: "",
                  ...f,
                });
                setOffset(0);
              }}
            >
              {!["applications", "review"].includes(view) && (
                <div className="grid">
                  <label>
                    Search
                    <input
                      name="q"
                      placeholder="Name, breed or description"
                      maxLength={100}
                    />
                  </label>
                  <label>
                    Species
                    <input
                      name="species"
                      placeholder="Dog, Cat…"
                      maxLength={100}
                    />
                  </label>
                  <label>
                    Location
                    <input name="location" maxLength={200} />
                  </label>
                  <label>
                    Maximum age in months
                    <input
                      name="max_age_months"
                      type="number"
                      min="0"
                      max="1200"
                    />
                  </label>
                </div>
              )}
              <label>
                Status
                <select name="status" defaultValue="">
                  {(view === "browse"
                    ? ["available", "reserved", "adopted"]
                    : ["applications", "review"].includes(view)
                      ? [
                          "all",
                          "pending",
                          "approved",
                          "rejected",
                          "withdrawn",
                          "completed",
                        ]
                      : view === "moderation"
                        ? [
                            "pending_review",
                            "all",
                            "available",
                            "reserved",
                            "adopted",
                            "rejected",
                            "archived",
                          ]
                        : [
                            "all",
                            "pending_review",
                            "available",
                            "reserved",
                            "adopted",
                            "rejected",
                            "archived",
                          ]
                  ).map((state, i) => (
                    <option key={state} value={i === 0 ? "" : state}>
                      {label(state)}
                    </option>
                  ))}
                </select>
              </label>
              {view === "moderation" && (
                <p>
                  Defaults to submissions awaiting approval. Select another
                  status to browse reviewed listings.
                </p>
              )}
              <button className="btn secondary" type="submit">
                Apply filters
              </button>
            </form>
          )}
          {selection && (
            <button
              className="btn ghost"
              onClick={() => {
                setSelection(null);
                setError("");
              }}
            >
              ← Back to results
            </button>
          )}
          {!data && !error && <p role="status">Loading adoption records…</p>}
          {data && selection?.type === "listing" && (
            <>
              <div className="two-col">
                <article className="card">
                  <Photo row={data} token={token} detail />
                  <h2>{data.name}</h2>
                  <span className="pill">{label(data.status)}</span>
                  <p>
                    {data.species} · {data.breed || "Breed not recorded"} ·{" "}
                    {data.age_months} months · {data.gender}
                  </p>
                  <p>{data.location}</p>
                  <p style={{ whiteSpace: "pre-wrap" }}>{data.description}</p>
                  <h3>Health summary</h3>
                  <p style={{ whiteSpace: "pre-wrap" }}>
                    {data.health_summary || "Not recorded"}
                  </p>
                  <p>
                    Weight:{" "}
                    {data.weight_kg ? `${data.weight_kg} kg` : "Not recorded"}
                  </p>
                  <p>Allergies: {data.allergies || "Not recorded"}</p>
                </article>
                <article className="card">
                  <h2>Next steps</h2>
                  {data.can_apply && (
                    <button
                      className="btn"
                      onClick={() =>
                        setEditor({ type: "application", row: data })
                      }
                    >
                      Apply to adopt
                    </button>
                  )}
                  {data.own_active_application_id && (
                    <button
                      className="btn secondary"
                      onClick={() =>
                        setSelection({
                          type: "application",
                          id: data.own_active_application_id,
                        })
                      }
                    >
                      View my application
                    </button>
                  )}
                  {data.can_manage && (
                    <>
                      <p>
                        Submitted by: {data.creator_name}<br />
                        Active applications: {data.active_application_count}
                      </p>
                      {data.moderation_reason && (
                        <p>Review note: {data.moderation_reason}</p>
                      )}
                      {data.can_edit && (
                        <>
                          <button
                            className="btn secondary"
                            disabled={busy}
                            onClick={() =>
                              setEditor({ type: "listing", row: data })
                            }
                          >
                            Edit listing
                          </button>
                          <label>
                            Upload JPEG/PNG photo (up to 5 MB)
                            <input
                              aria-label="Listing photo"
                              type="file"
                              accept="image/jpeg,image/png"
                              disabled={busy}
                              onChange={(event) => {
                                const file = event.target.files?.[0];
                                event.target.value = "";
                                if (!file) return;
                                if (file.size > 5 * 1024 * 1024) {
                                  setError("Select a photo smaller than 5 MB.");
                                  return;
                                }
                                const body = new FormData();
                                body.append("file", file);
                                void act(
                                  () =>
                                    api(
                                      `/adoption/listings/${data.id}/image?version=${data.version}`,
                                      "POST",
                                      body,
                                    ),
                                  owner
                                    ? "Photo saved; admin approval is required."
                                    : "Photo saved.",
                                );
                              }}
                            />
                          </label>
                          {owner && (
                            <p>
                              Editing this listing or its photo sends it for
                              admin review again.
                            </p>
                          )}
                        </>
                      )}
                      {admin && data.status === "pending_review" && (
                        <div className="actions">
                          <button
                            className="btn"
                            disabled={busy}
                            onClick={() => void review("approve")}
                          >
                            Approve publication
                          </button>
                          <button
                            className="btn danger"
                            disabled={busy}
                            onClick={() => void review("reject")}
                          >
                            Reject listing
                          </button>
                        </div>
                      )}
                      {editableStates.includes(data.status) && (
                        <button
                          className="btn danger"
                          disabled={busy}
                          onClick={() => void review("archive")}
                        >
                          Archive listing
                        </button>
                      )}
                    </>
                  )}
                  {admin && (
                    <button
                      className="btn secondary"
                      onClick={() => tab("review", data.id)}
                    >
                      Review applications for this animal
                    </button>
                  )}
                  {data.status === "reserved" && (
                    <p>This animal is reserved while handover is arranged.</p>
                  )}
                  {data.status === "adopted" && (
                    <p>This adoption is complete.</p>
                  )}
                  {!!data.history.length && (
                    <>
                      <h3>Listing history</h3>
                      {data.history.map((h) => (
                        <p key={h.id}>
                          {label(h.to_status)} · {when(h.created_at)}
                          <br />
                          {h.reason}
                        </p>
                      ))}
                    </>
                  )}
                </article>
              </div>
            </>
          )}
          {data && selection?.type === "application" && (
            <article className="card">
              <h2>
                {data.listing_name} · application #{data.id}
              </h2>
              <span className="pill">{label(data.status)}</span>
              <p>
                Applicant: {data.applicant_name} · {data.applicant_email}
              </p>
              <p>Contact: {data.contact_phone || "Not supplied"}</p>
              <p>
                Home: {data.housing} · Other pets:{" "}
                {data.has_other_pets ? "Yes" : "No"}
              </p>
              <h3>Adoption interest</h3>
              <p style={{ whiteSpace: "pre-wrap" }}>{data.motivation}</p>
              <h3>Experience</h3>
              <p style={{ whiteSpace: "pre-wrap" }}>
                {data.experience || "Not supplied"}
              </p>
              {data.decision_reason && (
                <p>Decision note: {data.decision_reason}</p>
              )}
              <div className="actions">
                <button
                  className="btn secondary"
                  onClick={() =>
                    setSelection({ type: "listing", id: data.listing_id })
                  }
                >
                  View animal
                </button>
                {data.applicant_id === user.id &&
                  ["pending", "approved"].includes(data.status) && (
                    <button
                      className="btn danger"
                      disabled={busy}
                      onClick={() => void decide("withdraw")}
                    >
                      Withdraw application
                    </button>
                  )}
                {admin && data.status === "pending" && (
                  <button
                    className="btn"
                    disabled={busy || data.listing_status !== "available"}
                    onClick={() => void decide("approve")}
                  >
                    Approve and reserve
                  </button>
                )}
                {admin && ["pending", "approved"].includes(data.status) && (
                  <button
                    className="btn danger"
                    disabled={busy}
                    onClick={() => void decide("reject")}
                  >
                    Reject application
                  </button>
                )}
                {admin && data.status === "approved" && (
                  <button
                    className="btn"
                    disabled={busy}
                    onClick={() => void decide("complete")}
                  >
                    Confirm handover completed
                  </button>
                )}
              </div>
              {data.status === "approved" && (
                <p>
                  Reserved. The administrator confirms completion after
                  handover.
                </p>
              )}
              {data.adopted_pet_id && (
                <p>
                  Adoption complete. The animal is now in the adopter’s My pets.
                </p>
              )}
              <h3>Application history</h3>
              {data.history.map((h) => (
                <p key={h.id}>
                  {label(h.to_status)} · {when(h.created_at)}
                  <br />
                  {h.reason}
                </p>
              ))}
            </article>
          )}
          {data && !selection && (
            <>
              <p>
                {data.total} result{data.total === 1 ? "" : "s"}
                {listingFilter ? " for the selected animal" : ""}
              </p>
              <div className="grid">
                {data.items.map((row) => {
                  const application = ["applications", "review"].includes(view);
                  return (
                    <article className="card" key={row.id}>
                      {!application && <Photo row={row} token={token} />}
                      <h2>{application ? row.listing_name : row.name}</h2>
                      <span className="pill">{label(row.status)}</span>
                      {application ? (
                        <p>
                          Application #{row.id} ·{" "}
                          {admin ? row.applicant_name : "Your application"}
                        </p>
                      ) : (
                        <p>
                          {row.species} · {row.age_months} months
                          <br />
                          {row.location}
                        </p>
                      )}
                      <button
                        className="btn secondary"
                        onClick={() => {
                          setSelection({
                            type: application ? "application" : "listing",
                            id: row.id,
                          });
                          setError("");
                        }}
                      >
                        View {application ? "application" : "animal"}
                      </button>
                    </article>
                  );
                })}
              </div>
              {!data.items.length && (
                <div className="empty">
                  No adoption records match this view.
                </div>
              )}
              <div className="actions">
                {offset > 0 && (
                  <button
                    className="btn secondary"
                    onClick={() => setOffset((x) => Math.max(0, x - 12))}
                  >
                    Previous page
                  </button>
                )}
                {offset + data.items.length < data.total && (
                  <button
                    className="btn secondary"
                    onClick={() => setOffset((x) => x + 12)}
                  >
                    Next page
                  </button>
                )}
              </div>
            </>
          )}
          {error && (
            <button className="btn secondary" onClick={refresh}>
              Try again
            </button>
          )}
        </>
      )}
    </section>
  );
}
