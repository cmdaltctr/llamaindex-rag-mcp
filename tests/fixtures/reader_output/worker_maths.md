And:

 $$ \begin{align*}\int q_{\boldsymbol{\theta}}(\mathbf{z})\log q_{\boldsymbol{\theta}}(\mathbf{z})d\mathbf{z}=&\int\mathcal{N}(\mathbf{z};\boldsymbol{\mu},\boldsymbol{\sigma}^{2})\log\mathcal{N}(\mathbf{z};\boldsymbol{\mu},\boldsymbol{\sigma}^{2})d\mathbf{z}\\ =&-\frac{J}{2}\log(2\pi)-\frac{1}{2}\sum_{j=1}^{J}(1+\log\sigma_{j}^{2})\end{align*} $$ 

When using a recognition model  $ q_{\phi}(\mathbf{z}|\mathbf{x}) $ then  $ \mu $ and s.d.  $ \sigma $ are simply functions of  $ \mathbf{x} $ and the variational parameters  $ \phi $, as exemplified in the text.
