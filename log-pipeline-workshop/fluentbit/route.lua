local levels = {TRACE=true, DEBUG=true, INFO=true, WARN=true, WARNING=true,
                ERROR=true, CRITICAL=true, FATAL=true}

function route(tag, timestamp, record)
    local service = tag:match('^input%.([a-z_]+)$')
    if not service then
        return -1, timestamp, record
    end
    -- Tail wraps lines rejected by the JSON parser in a lone `log` field.
    if record.log ~= nil and record.event == nil and record.level == nil and record.message == nil then
        return -1, timestamp, record
    end
    record.source_service = service
    local status = record.regex_status
    if (status == 'gerai' or status == 'klaida')
       and (record.event == 'salary_export' or record.event == 'invoice_created') then
        -- A new record prevents unknown fields, keys, arrays or nested PII escaping.
        local clean = {source_service=service, processing_path='regex', _route='regex',
                       event=record.event, message='[REDACTED]', status=status}
        if type(record.level) == 'string' and levels[record.level:upper()] then
            clean.level = record.level:upper()
        end
        if type(record.sequence) == 'number' and record.sequence >= 0
           and record.sequence <= 9007199254740991 and record.sequence % 1 == 0 then
            clean.sequence = record.sequence
        end
        return 2, timestamp, clean
    end
    record.regex_status = nil
    record._route = 'presidio'
    return 2, timestamp, record
end
