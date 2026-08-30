"use client";

import { useState, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { UploadCloud, CheckCircle2, FileText, Loader2, BarChart3, AlertTriangle, ArrowRight } from "lucide-react";
import { cn } from "@/lib/utils";

type Status = "IDLE" | "UPLOADING" | "PROCESSING" | "COMPLETED" | "ERROR";

export default function ReconcileApp() {
  const [status, setStatus] = useState<Status>("IDLE");
  const [files, setFiles] = useState<{ bank: File | null; gl: File | null; inv: File | null }>({ bank: null, gl: null, inv: null });
  const [jobId, setJobId] = useState<string | null>(null);
  const [report, setReport] = useState<any>(null);
  const [errorMsg, setErrorMsg] = useState("");

  const handleFile = (type: "bank" | "gl" | "inv", e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFiles((prev) => ({ ...prev, [type]: e.target.files![0] }));
    }
  };

  const allFilesSelected = files.bank && files.gl && files.inv;

  const startReconciliation = async () => {
    setStatus("UPLOADING");
    try {
      const formData = new FormData();
      formData.append("bank_statements", files.bank!);
      formData.append("gl_ledger", files.gl!);
      formData.append("invoices", files.inv!);

      const res = await fetch("http://127.0.0.1:8000/api/reconcile/start/", {
        method: "POST",
        body: formData,
      });

      const data = await res.json();
      if (res.ok) {
        setJobId(data.id);
        setStatus("PROCESSING");
      } else {
        throw new Error(data.error || "Failed to start job");
      }
    } catch (err: any) {
      setErrorMsg(err.message);
      setStatus("ERROR");
    }
  };

  useEffect(() => {
    if (status === "PROCESSING" && jobId) {
      const interval = setInterval(async () => {
        try {
          const res = await fetch(`http://127.0.0.1:8000/api/reconcile/status/${jobId}/`);
          const data = await res.json();
          if (data.status === "COMPLETED") {
            setReport(data.report);
            setStatus("COMPLETED");
            clearInterval(interval);
          } else if (data.status === "FAILED") {
            setErrorMsg(data.error_message || "Reconciliation job failed.");
            setStatus("ERROR");
            clearInterval(interval);
          }
        } catch (err) {
          console.error("Polling error", err);
        }
      }, 2000);
      return () => clearInterval(interval);
    }
  }, [status, jobId]);

  return (
    <div className="min-h-screen bg-[#09090b] text-zinc-100 flex flex-col items-center pt-24 pb-12 px-6 overflow-hidden">
      
      {/* Premium Gradient Glow */}
      <div className="absolute top-[-20%] left-[50%] translate-x-[-50%] w-[800px] h-[500px] bg-zinc-800/40 rounded-full blur-[120px] pointer-events-none" />

      <motion.div 
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
        className="w-full max-w-5xl z-10"
      >
        <header className="mb-16 text-center">
          <motion.div 
            initial={{ scale: 0.9, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ delay: 0.2, duration: 0.6 }}
            className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-zinc-900 border border-zinc-800 text-xs font-medium text-zinc-400 mb-6"
          >
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            System Operational
          </motion.div>
          <h1 className="text-4xl md:text-5xl font-light tracking-tight mb-4 text-white">
            Reconciliation <span className="font-medium text-zinc-500">Engine</span>
          </h1>
          <p className="text-zinc-500 max-w-xl mx-auto font-light">
            Securely upload your ledgers. Our XGBoost matcher and AI triage agent will handle the anomalies instantly.
          </p>
        </header>

        <AnimatePresence mode="wait">
          {(status === "IDLE" || status === "UPLOADING") && (
            <motion.div
              key="uploader"
              initial={{ opacity: 0, filter: "blur(10px)" }}
              animate={{ opacity: 1, filter: "blur(0px)" }}
              exit={{ opacity: 0, scale: 0.98, filter: "blur(5px)" }}
              transition={{ duration: 0.5 }}
              className="grid gap-6 md:grid-cols-3"
            >
              <UploadCard title="Bank Statement" id="bank" file={files.bank} onChange={(e) => handleFile("bank", e)} delay={0.1} />
              <UploadCard title="GL Ledger" id="gl" file={files.gl} onChange={(e) => handleFile("gl", e)} delay={0.2} />
              <UploadCard title="Invoices" id="inv" file={files.inv} onChange={(e) => handleFile("inv", e)} delay={0.3} />

              <div className="col-span-1 md:col-span-3 flex justify-center mt-8">
                <button
                  onClick={startReconciliation}
                  disabled={!allFilesSelected || status === "UPLOADING"}
                  className={cn(
                    "group relative flex items-center gap-3 px-8 py-4 rounded-2xl font-medium tracking-wide transition-all duration-500",
                    allFilesSelected 
                      ? "bg-zinc-100 text-zinc-950 hover:bg-white hover:scale-[1.02] shadow-[0_0_40px_-10px_rgba(255,255,255,0.3)]"
                      : "bg-zinc-900 text-zinc-600 cursor-not-allowed border border-zinc-800"
                  )}
                >
                  {status === "UPLOADING" ? (
                    <Loader2 className="w-5 h-5 animate-spin" />
                  ) : (
                    <>
                      Commence Analysis
                      <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-1" />
                    </>
                  )}
                </button>
              </div>
            </motion.div>
          )}

          {status === "PROCESSING" && (
            <motion.div
              key="processing"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              className="flex flex-col items-center justify-center py-24"
            >
              <div className="relative w-32 h-32 flex items-center justify-center">
                <motion.div 
                  animate={{ rotate: 360 }}
                  transition={{ repeat: Infinity, duration: 8, ease: "linear" }}
                  className="absolute inset-0 rounded-full border border-dashed border-zinc-700"
                />
                <motion.div 
                  animate={{ rotate: -360 }}
                  transition={{ repeat: Infinity, duration: 12, ease: "linear" }}
                  className="absolute inset-4 rounded-full border border-zinc-600"
                />
                <Loader2 className="w-8 h-8 text-zinc-300 animate-spin" />
              </div>
              <h3 className="mt-8 text-xl font-light text-zinc-300 tracking-wide animate-pulse">Running pairwise ML matcher...</h3>
              <p className="text-zinc-600 mt-2 text-sm">Delegating exceptions to LLM triage agent</p>
            </motion.div>
          )}

          {status === "COMPLETED" && report && (
            <motion.div
              key="completed"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.6 }}
              className="space-y-8"
            >
              {/* Top Stats */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <StatCard label="Total Transactions" value={report.batch_size} icon={<BarChart3 />} delay={0} />
                <StatCard label="Match Rate" value={`${(report.match_rate * 100).toFixed(1)}%`} icon={<CheckCircle2 className="text-emerald-500" />} delay={0.1} />
                <StatCard label="Exceptions Found" value={`${(report.exception_rate * 100).toFixed(1)}%`} icon={<AlertTriangle className="text-amber-500" />} delay={0.2} />
              </div>

              {/* Exception Table */}
              <motion.div 
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.4 }}
                className="bg-zinc-900/40 border border-zinc-800/60 rounded-3xl overflow-hidden backdrop-blur-xl"
              >
                <div className="px-8 py-6 border-b border-zinc-800/60 flex items-center justify-between">
                  <h3 className="font-medium text-zinc-100 flex items-center gap-2">
                    <AlertTriangle className="w-4 h-4 text-amber-500" />
                    Flagged Exceptions
                  </h3>
                  <span className="text-xs text-zinc-500 font-mono bg-zinc-950 px-2 py-1 rounded-md border border-zinc-800">
                    {report.exceptions.length} records requiring human review
                  </span>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm whitespace-nowrap">
                    <thead className="bg-zinc-950/50 text-zinc-500 text-xs tracking-wider uppercase">
                      <tr>
                        <th className="px-8 py-4 font-medium">Txn ID</th>
                        <th className="px-8 py-4 font-medium">Date</th>
                        <th className="px-8 py-4 font-medium">Counterparty</th>
                        <th className="px-8 py-4 font-medium text-right">Amount</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-zinc-800/60 text-zinc-300">
                      {report.exceptions.map((ex: any, i: number) => (
                        <motion.tr 
                          initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.5 + (i * 0.05) }}
                          key={ex.txn_id} 
                          className="hover:bg-zinc-800/30 transition-colors"
                        >
                          <td className="px-8 py-4 font-mono text-zinc-400">{ex.txn_id}</td>
                          <td className="px-8 py-4">{new Date(ex.date).toLocaleDateString()}</td>
                          <td className="px-8 py-4">{ex.counterparty}</td>
                          <td className="px-8 py-4 text-right font-mono">${ex.amount.toFixed(2)}</td>
                        </motion.tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </motion.div>
              
              <div className="flex justify-center mt-12">
                 <button onClick={() => setStatus("IDLE")} className="text-sm text-zinc-500 hover:text-zinc-300 transition-colors">
                   ← Start New Run
                 </button>
              </div>
            </motion.div>
          )}

          {status === "ERROR" && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="text-center py-24">
              <AlertCircle className="w-12 h-12 text-red-500 mx-auto mb-4" />
              <h3 className="text-xl text-zinc-100 font-medium">System Failure</h3>
              <p className="text-zinc-500 mt-2">{errorMsg}</p>
              <button onClick={() => setStatus("IDLE")} className="mt-8 px-6 py-2 bg-zinc-900 border border-zinc-800 rounded-full hover:bg-zinc-800 transition">
                Try Again
              </button>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>
    </div>
  );
}

// ---------------- Components ----------------

function UploadCard({ title, id, file, onChange, delay }: any) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay, duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
      className="relative group h-48 rounded-3xl bg-zinc-900/30 border border-zinc-800/60 hover:bg-zinc-900/50 hover:border-zinc-700/60 transition-all backdrop-blur-md overflow-hidden flex flex-col items-center justify-center p-6 text-center cursor-pointer"
    >
      <input type="file" id={id} onChange={onChange} accept=".csv" className="absolute inset-0 opacity-0 cursor-pointer z-10" />
      
      {file ? (
        <motion.div initial={{ scale: 0.8, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} className="flex flex-col items-center gap-3">
          <div className="w-12 h-12 rounded-full bg-emerald-500/10 flex items-center justify-center text-emerald-500">
            <CheckCircle2 className="w-6 h-6" />
          </div>
          <div className="space-y-1">
            <p className="text-zinc-100 font-medium text-sm">{file.name}</p>
            <p className="text-zinc-600 text-xs font-mono">{(file.size / 1024).toFixed(1)} KB</p>
          </div>
        </motion.div>
      ) : (
        <div className="flex flex-col items-center gap-4 text-zinc-500 group-hover:text-zinc-300 transition-colors">
          <div className="w-12 h-12 rounded-full bg-zinc-800/50 flex items-center justify-center group-hover:bg-zinc-800 transition-colors">
            <UploadCloud className="w-5 h-5" />
          </div>
          <p className="text-sm tracking-wide font-light">Upload {title}</p>
        </div>
      )}
    </motion.div>
  );
}

function StatCard({ label, value, icon, delay }: any) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.1 + delay, duration: 0.6 }}
      className="bg-zinc-900/40 border border-zinc-800/60 rounded-3xl p-6 backdrop-blur-xl flex flex-col"
    >
      <div className="flex justify-between items-start mb-4">
        <span className="text-zinc-500 text-sm">{label}</span>
        <div className="text-zinc-600">{icon}</div>
      </div>
      <div className="text-3xl font-light tracking-tight text-zinc-100 mt-auto">
        {value}
      </div>
    </motion.div>
  );
}
