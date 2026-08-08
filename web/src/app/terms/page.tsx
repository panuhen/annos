import type { Metadata } from "next";

import { ContactEmail } from "@/components/contact-email";
import { LegalLayout } from "@/components/legal-layout";

export const metadata: Metadata = {
  title: "Terms of Service · Annos",
  description: "The terms for using the free, open-source Annos service.",
};

export default function TermsPage() {
  return (
    <LegalLayout title="Terms of Service" lastUpdated="2026-08-08">
      <section>
        <h2>1. Acceptance</h2>
        <p>
          By accessing or using Annos you agree to these Terms. If you do not agree, please do not
          use it.
        </p>
      </section>

      <section>
        <h2>2. What Annos is</h2>
        <p>
          Annos is a free, non-commercial food, exercise and weight tracker, available on the web
          and to AI clients over MCP; both work on the same account and the same data. It is
          open-source software, released under the MIT License, with the source available at{" "}
          <a href="https://github.com/panuhen/annos" rel="noopener">
            github.com/panuhen/annos
          </a>
          . Anyone may run their own copy; these Terms cover the hosted service at annos.app.
        </p>
      </section>

      <section>
        <h2>3. Not medical advice</h2>
        <p>
          <strong>
            Annos is not a medical device and does not provide medical, nutritional, or health
            advice.
          </strong>{" "}
          It records what you log and returns arithmetic — totals, targets, and trends — and nothing
          more. It is not a substitute for a doctor, dietitian, or other qualified professional, and
          must not be used to diagnose, treat, or prevent any condition. Any decision you make using
          Annos is your own. If you have a health concern, consult a professional.
        </p>
      </section>

      <section>
        <h2>4. Your account</h2>
        <p>
          Accounts are pseudonymous — Annos never asks for your real name. You are responsible for
          keeping your sign-in credentials safe and for activity under your account, and you agree
          to tell us if you believe it has been accessed without your permission. Registration is
          available only through the web interface.
        </p>
      </section>

      <section>
        <h2>5. Acceptable use</h2>
        <p>You agree not to:</p>
        <ul>
          <li>use Annos for any unlawful or harmful purpose;</li>
          <li>probe, scan, overload, or disrupt the service or its infrastructure;</li>
          <li>attempt to gain unauthorised access to other accounts or to the systems behind it;</li>
          <li>reverse engineer or circumvent limits of the hosted service (the source is open, so there is no need to).</li>
        </ul>
        <p>
          When you connect an AI client over MCP, it acts as you and with your access — you are
          responsible for what it does on your account.
        </p>
      </section>

      <section>
        <h2>6. Your data</h2>
        <p>
          You own the data you log. You can export all of it, or delete it and your account
          entirely, at any time, from your profile page. We host and process it only to provide
          Annos to you, and never use it to train machine-learning models. How it is handled is
          described in our <a href="/privacy">Privacy Policy</a>.
        </p>
      </section>

      <section>
        <h2>7. No warranty</h2>
        <p>
          Annos is provided free of charge, <strong>&quot;as is&quot; and &quot;as available&quot;</strong>,
          without warranty of any kind, whether express, implied, or statutory, including any implied
          warranty of merchantability, fitness for a particular purpose, or non-infringement. This
          matches the MIT License the software is released under. We do not warrant that the service
          will be uninterrupted, error-free, or that any calculation it shows is accurate, and we may
          change, suspend, or discontinue any part of it at any time.
        </p>
      </section>

      <section>
        <h2>8. Limitation of liability</h2>
        <p>
          To the fullest extent permitted by law, the operator and contributors of Annos are not
          liable for any indirect, incidental, special, consequential, or punitive damages, nor for
          any loss of data, arising from your use of — or inability to use — the service, even where
          the possibility was known. Because Annos is provided free of charge, its total liability to
          you is limited to zero, except for liability that cannot be excluded under applicable law
          (including mandatory data-protection and consumer rights).
        </p>
      </section>

      <section>
        <h2>9. Data protection</h2>
        <p>
          For the hosted service, we act as data controller for your account and the data you log,
          and process personal data in the European Union. Your rights and how the data is handled
          are set out in the <a href="/privacy">Privacy Policy</a>. Nothing in these Terms limits
          rights you have under the GDPR.
        </p>
      </section>

      <section>
        <h2>10. Ending your use</h2>
        <p>
          You may delete your account at any time — it is immediate and permanent. We may suspend or
          end access to the hosted service to protect it from abuse or a security risk, or if you
          breach these Terms. Sections 3, 7, 8, and 11 survive.
        </p>
      </section>

      <section>
        <h2>11. Governing law</h2>
        <p>
          These Terms are governed by the laws of Finland, without regard to conflict-of-law rules,
          and the courts of Finland have jurisdiction — except where mandatory consumer law gives
          you the right to your local courts.
        </p>
      </section>

      <section>
        <h2>12. Changes and contact</h2>
        <p>
          We may update these Terms; where a change is material we will make it visible in the app,
          and continued use afterwards means you accept it. For any question about these Terms,
          contact us at <ContactEmail />.
        </p>
      </section>
    </LegalLayout>
  );
}
