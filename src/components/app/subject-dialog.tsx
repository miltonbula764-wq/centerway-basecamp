import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";
import { Loader2 } from "lucide-react";
import { supabase } from "@/integrations/supabase/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { assertActiveTenant, tk, useTenant } from "@/lib/tenant";
import { friendlyError } from "@/lib/errors";
import { ErrorState, FieldHint } from "./ui-bits";
import { toast } from "sonner";

type Subject = { id: string; external_ref: string; display_name: string | null };

export function SubjectDialog({ open, onOpenChange, subject }: { open: boolean; onOpenChange: (o: boolean) => void; subject?: Subject | undefined }) {
  const { tenant } = useTenant();
  const tenantId = tenant.id; // captured at open time
  const qc = useQueryClient();
  const [ref, setRef] = useState("");
  const [name, setName] = useState("");

  useEffect(() => {
    if (open) {
      setRef(subject?.external_ref ?? "");
      setName(subject?.display_name ?? "");
    }
  }, [open, subject]);

  const save = useMutation({
    mutationFn: async () => {
      assertActiveTenant(tenantId);
      const display_name = name.trim() || null;
      if (subject) {
        const { error } = await supabase.from("subjects").update({ display_name }).eq("id", subject.id).eq("tenant_id", tenantId);
        if (error) throw error;
      } else {
        const { error } = await supabase.from("subjects").insert({ tenant_id: tenantId, external_ref: ref.trim(), display_name });
        if (error) throw error;
      }
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: tk(tenantId, "subjects") });
      qc.invalidateQueries({ queryKey: tk(tenantId, "subject") });
      qc.invalidateQueries({ queryKey: tk(tenantId, "count") });
      toast.success(subject ? "Cliente atualizado." : "Cliente criado.");
      onOpenChange(false);
    },
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!subject && !ref.trim()) return;
    save.mutate();
  }

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) save.reset(); onOpenChange(o); }}>
      <DialogContent>
        <form onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>{subject ? "Editar cliente" : "Novo cliente"}</DialogTitle>
            <DialogDescription>
              {tenant.subject_unit_type === "person" ? "Uma pessoa acompanhada" : "Uma organização acompanhada"} em {tenant.name}.
            </DialogDescription>
          </DialogHeader>
          <div className="my-5 space-y-4">
            <div>
              <Label htmlFor="ext">Referência externa</Label>
              <Input id="ext" value={ref} onChange={(e) => setRef(e.target.value)} maxLength={200} disabled={!!subject} className="mt-1.5 font-mono" required />
              <FieldHint>
                {subject
                  ? "A referência identifica o cliente nas fontes de dados e não é editável aqui."
                  : "O ID deste cliente no seu sistema (ex.: CRM ou faturação). Única por empresa."}
              </FieldHint>
            </div>
            <div>
              <Label htmlFor="dn">Nome a apresentar (opcional)</Label>
              <Input id="dn" value={name} onChange={(e) => setName(e.target.value)} maxLength={300} className="mt-1.5" />
            </div>
            {save.isError && <ErrorState message={friendlyError(save.error, "subject")} />}
          </div>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>Cancelar</Button>
            <Button type="submit" disabled={save.isPending || (!subject && !ref.trim())}>
              {save.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              Guardar
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
