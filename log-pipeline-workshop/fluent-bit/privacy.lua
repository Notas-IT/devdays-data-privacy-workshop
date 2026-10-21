local fields = {"employee_name", "national_id", "email", "phone", "address",
                "salary_eur", "company_profit_eur"}
local sources = { ["app.hr"] = "hr", ["app.billing"] = "billing" }
local events = { hr = "salary_export", billing = "invoice_created" }
local levels = { INFO = true, WARN = true, ERROR = true, DEBUG = true }
local policy_path = os.getenv("POLICY_PATH") or "/config/active.lua"

local function load_policy()
    local chunk = loadfile(policy_path)
    if not chunk then return nil end
    -- Policies are trusted operator-managed files, evaluated without globals.
    setfenv(chunk, {})
    local ok, policy = pcall(chunk)
    if not ok or type(policy) ~= "table" then return nil end
    local allowed = {version = true, message_action = true, field_actions = true}
    for key in pairs(policy) do
        if not allowed[key] then return nil end
    end
    if type(policy.version) ~= "string" or #policy.version < 1 or #policy.version > 32
       or not policy.version:match("^[a-z0-9_-]+$") then return nil end
    if policy.message_action ~= "replace" and policy.message_action ~= "drop"
       and policy.message_action ~= "summary" then return nil end
    if type(policy.field_actions) ~= "table" then return nil end
    local known = {}
    for _, key in ipairs(fields) do known[key] = true end
    for key, action in pairs(policy.field_actions) do
        if not known[key] or (action ~= "replace" and action ~= "drop") then return nil end
    end
    return policy
end

local function transform(tag, record)
    local policy = load_policy()
    local service = sources[tag]
    if not policy or not service or type(record) ~= "table" then return nil end
    -- Unparsed/malformed input has only a raw 'log' field: discard it entirely.
    if type(record.message) ~= "string" or type(record.event) ~= "string"
       or type(record.level) ~= "string" then return nil end
    local event = record.event == events[service] and events[service] or "unknown"
    local output = {service = service, event = event,
                    level = levels[record.level] and record.level or "INFO",
                    policy_version = policy.version, pipeline_guard = "sanitized-v1"}
    for _, key in ipairs(fields) do
        if policy.field_actions[key] == "replace" and record[key] ~= nil then
            output[key] = "<REDACTED>"
        end
    end
    if policy.message_action == "replace" then
        output.message = "<REDACTED_MESSAGE>"
    elseif policy.message_action == "summary" then
        output.message = "Processed event: " .. event
    end
    return output
end

function sanitize(tag, timestamp, record)
    local ok, output = pcall(transform, tag, record)
    if not ok or not output then return -1, timestamp, {} end
    return 2, timestamp, output
end
