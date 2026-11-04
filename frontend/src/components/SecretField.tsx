import { useState } from 'react';
import { Button, Input, Label, TextField } from '@heroui/react';
import { Eye, EyeOff } from 'lucide-react';
type Props = {
    label: string;
    value: string;
    onChange(value: string): void;
    name?: string;
    error?: string;
    autoComplete?: string;
};
export function SecretField({ label, value, onChange, name, error, autoComplete }: Props) {
    const [visible, setVisible] = useState(false);
    const [copied, setCopied] = useState(false);
    const copy = async () => {
        if (!value)
            return;
        await navigator.clipboard.writeText(value);
        setCopied(true);
        window.setTimeout(() => setCopied(false), 1200);
    };
    const toggleLabel = `${visible ? 'Hide' : 'Show'} ${label.toLowerCase()}`;
    return (
        <TextField name={name} isInvalid={Boolean(error)}>
            <Label>{label}</Label>
            <div className="secret-field-row">
                <Input type={visible ? 'text' : 'password'} value={value} onChange={e => onChange(e.target.value)} autoComplete={autoComplete}/>
                <Button type="button" variant="ghost" size="sm" isIconOnly className="secret-field-toggle" aria-label={toggleLabel} onPress={() => setVisible(v => !v)}>
                    {visible ? <EyeOff size={16} aria-hidden="true" /> : <Eye size={16} aria-hidden="true" />}
                </Button>
                <Button type="button" variant="ghost" size="sm" isDisabled={!value} onPress={() => void copy()}>{copied ? 'Copied' : 'Copy'}</Button>
            </div>
            {error ? <p className="field-error" role="alert">{error}</p> : null}
        </TextField>
    );
}
